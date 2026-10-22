"""Voluntary gift collections. The birthday person is never invited."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rules import (
    eligible_collection_participants,
    hr_collection_view,
    initial_delivery_status,
    peer_collection_view,
)
from app.errors import DomainError, NotFoundError
from app.models import Collection, CollectionParticipant, Employee, utcnow
from app.ports import Button, PermanentDeliveryError, TransientTelegramError
from app.services.audit import write_audit
from app.services.org import get_org, payment_details_text

OPEN_RESPONSES = {"accepted", "payment_declared", "confirmed"}


def create_collection(
    session: Session,
    *,
    employee_id: UUID,
    title: str,
    description: str,
    deadline: date | None,
    scope: dict | None,
    actor_id: UUID | None,
) -> Collection:
    """Payment method, phone, and fixed amount always come from the organization."""
    _birthday_employee(session, employee_id)
    org = get_org(session)
    collection = Collection(
        employee_id=employee_id,
        title=title.strip(),
        description=(description or "").strip(),
        contribution_mode="fixed",
        fixed_amount=org.payment_fixed_amount,
        currency=(org.currency or "KZT").upper(),
        deadline=deadline,
        status="draft",
        scope=_scope(scope),
        payment_details=payment_details_text(org.payment_phone),
        created_by=actor_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(collection)
    write_audit(session, actor_id, "collection.create", "collection", collection.id, {"status": "draft"})
    session.commit()
    return collection


def update_collection(session: Session, collection_id: UUID, changes: dict, actor_id: UUID | None) -> Collection:
    collection = _get(session, collection_id)
    if collection.status != "draft":
        raise DomainError("Менять условия можно только у черновика")
    for locked in ("payment_details", "contribution_mode", "fixed_amount", "currency"):
        changes.pop(locked, None)
    if "title" in changes and changes["title"]:
        collection.title = str(changes["title"]).strip()
    if "description" in changes and changes["description"] is not None:
        collection.description = str(changes["description"]).strip()
    if "payment_details" in changes and changes["payment_details"] is not None:
        collection.payment_details = str(changes["payment_details"]).strip()
    if "deadline" in changes:
        collection.deadline = changes["deadline"]
    if "currency" in changes and changes["currency"]:
        collection.currency = str(changes["currency"]).upper()
    if "scope" in changes and changes["scope"] is not None:
        collection.scope = _scope(changes["scope"])
    if "contribution_mode" in changes or "fixed_amount" in changes:
        mode = changes.get("contribution_mode", collection.contribution_mode)
        amount = changes["fixed_amount"] if "fixed_amount" in changes else collection.fixed_amount
        collection.contribution_mode = _mode(mode, amount)
        collection.fixed_amount = amount if collection.contribution_mode == "fixed" else None
    collection.updated_at = utcnow()
    write_audit(session, actor_id, "collection.update", "collection", collection.id, {})
    session.commit()
    return collection


def open_collection(session: Session, collection_id: UUID, sender, actor_id: UUID | None) -> Collection:
    collection = session.get(Collection, collection_id, with_for_update=True)
    if collection is None:
        raise NotFoundError("Сбор не найден")
    if collection.status != "draft":
        raise DomainError("Сбор можно открыть только из черновика")
    _apply_org_payment(session, collection)
    if not collection.payment_details.strip() or collection.fixed_amount is None:
        raise DomainError("В настройках организации нет реквизитов или фиксированного взноса")
    employees = list(session.scalars(select(Employee)))
    selected_ids = {
        row["id"]
        for row in eligible_collection_participants(
            [_employee_dict(item) for item in employees],
            str(collection.employee_id),
            collection.scope,
        )
    }
    if not selected_ids:
        raise DomainError("Нет участников: именинник исключён, а других подходящих сотрудников нет")
    by_id = {str(item.id): item for item in employees}
    collection.status = "open"
    collection.opened_at = utcnow()
    collection.updated_at = utcnow()
    for employee_id in selected_ids:
        employee = by_id[employee_id]
        session.add(
            CollectionParticipant(
                collection_id=collection.id,
                employee_id=employee.id,
                status="invited",
                delivery_status=initial_delivery_status(_employee_dict(employee), "collections"),
                created_at=utcnow(),
                updated_at=utcnow(),
            )
        )
    write_audit(session, actor_id, "collection.open", "collection", collection.id, {"participants": len(selected_ids)})
    session.commit()
    dispatch_invites(session, collection.id, sender)
    return collection


def dispatch_invites(session: Session, collection_id: UUID, sender) -> None:
    collection = _get(session, collection_id)
    if collection.status != "open":
        return
    participants = list(
        session.scalars(select(CollectionParticipant).where(CollectionParticipant.collection_id == collection.id))
    )
    for participant in participants:
        if participant.delivery_status != "pending":
            continue
        employee = session.get(Employee, participant.employee_id)
        if employee is None or not employee.telegram_id:
            participant.delivery_status = "not_started"
            participant.updated_at = utcnow()
            session.commit()
            continue
        participant.delivery_status = "sending"
        participant.updated_at = utcnow()
        session.commit()
        buttons = [
            [
                Button("Участвовать", f"c:a:{collection.id}"),
                Button("Пропустить", f"c:d:{collection.id}"),
            ]
        ]
        text = _invite_text(collection)
        try:
            result = sender.send_message(int(employee.telegram_id), text, buttons=buttons)
        except TransientTelegramError:
            participant.delivery_status = "failed"
            participant.updated_at = utcnow()
            session.commit()
            continue
        except PermanentDeliveryError as exc:
            participant.delivery_status = _permanent_status(exc.code)
            if exc.code == "blocked":
                employee.bot_status = "blocked"
                employee.updated_at = utcnow()
            participant.updated_at = utcnow()
            session.commit()
            continue
        participant.delivery_status = "simulated" if result.simulated or result.provider == "test" else "sent"
        participant.provider = result.provider
        participant.telegram_message_id = result.message_id
        participant.updated_at = utcnow()
        session.commit()


def respond(session: Session, collection_id: UUID, employee_id: UUID, decision: str) -> CollectionParticipant:
    collection = _open_collection(session, collection_id)
    participant = _participant(session, collection.id, employee_id)
    if decision == "decline":
        participant.status = "declined"
        participant.amount = None
    elif decision == "accept":
        participant.status = "accepted"
    else:
        raise DomainError("Нужно выбрать участие или отказ")
    participant.updated_at = utcnow()
    session.commit()
    return participant


def declare_payment(session: Session, collection_id: UUID, employee_id: UUID, amount: Decimal | None) -> CollectionParticipant:
    collection = _open_collection(session, collection_id)
    participant = _participant(session, collection.id, employee_id)
    if participant.status not in {"accepted", "payment_declared"}:
        raise DomainError("Сначала нажмите «Участвовать»")
    if collection.contribution_mode == "fixed":
        participant.amount = collection.fixed_amount
    else:
        if amount is None or amount <= 0:
            raise DomainError("Укажите сумму перевода")
        participant.amount = amount
    participant.status = "payment_declared"
    participant.updated_at = utcnow()
    session.commit()
    return participant


def confirm_payment(session: Session, participant_id: UUID, actor_id: UUID | None, amount: Decimal | None = None) -> CollectionParticipant:
    participant = session.get(CollectionParticipant, participant_id)
    if participant is None:
        raise NotFoundError("Участник не найден")
    collection = _get(session, participant.collection_id)
    if collection.status not in {"open", "closed"}:
        raise DomainError("Сбор не принимает подтверждения")
    if amount is not None:
        participant.amount = amount
    if participant.amount is None:
        raise DomainError("Нет суммы для подтверждения")
    participant.status = "confirmed"
    participant.updated_at = utcnow()
    write_audit(
        session,
        actor_id,
        "collection.confirm_payment",
        "collection_participant",
        participant.id,
        {"collection_id": str(collection.id)},
    )
    session.commit()
    return participant


def close_collection(session: Session, collection_id: UUID, actor_id: UUID | None) -> Collection:
    collection = _get(session, collection_id)
    if collection.status != "open":
        raise DomainError("Закрыть можно только открытый сбор")
    collection.status = "closed"
    collection.closed_at = utcnow()
    collection.updated_at = utcnow()
    write_audit(session, actor_id, "collection.close", "collection", collection.id, {})
    session.commit()
    return collection


def cancel_collection(session: Session, collection_id: UUID, actor_id: UUID | None) -> Collection:
    collection = _get(session, collection_id)
    if collection.status in {"closed", "cancelled"}:
        raise DomainError("Сбор уже завершён")
    if collection.status == "open":
        collection.closed_at = utcnow()
    collection.status = "cancelled"
    collection.updated_at = utcnow()
    write_audit(session, actor_id, "collection.cancel", "collection", collection.id, {})
    session.commit()
    return collection


def hr_view(session: Session, collection_id: UUID) -> dict:
    collection = _get(session, collection_id)
    participants = _participant_rows(session, collection)
    return hr_collection_view(_collection_dict(collection), participants)


def peer_view(session: Session, collection_id: UUID, employee_id: UUID) -> dict:
    collection = _get(session, collection_id)
    participant = _participant(session, collection.id, employee_id)
    own = next(row for row in _participant_rows(session, collection) if row["employee_id"] == str(employee_id))
    return peer_collection_view(_collection_dict(collection), own)


def list_collections(session: Session) -> list[Collection]:
    return list(session.scalars(select(Collection).order_by(Collection.created_at.desc())))


def _invite_text(collection: Collection) -> str:
    deadline = f" Срок: {collection.deadline.isoformat()}." if collection.deadline else ""
    money = f" Фиксированный взнос: {collection.fixed_amount} {collection.currency}."
    details = f" {collection.payment_details}." if collection.payment_details else ""
    return (
        f"{collection.title}. Участие добровольное, отказ объяснять не нужно.{money}{details}{deadline}\n"
        f"{collection.description}".strip()
    )


def _apply_org_payment(session: Session, collection: Collection) -> None:
    org = get_org(session)
    collection.contribution_mode = "fixed"
    collection.fixed_amount = org.payment_fixed_amount
    collection.currency = (org.currency or "KZT").upper()
    collection.payment_details = payment_details_text(org.payment_phone)
    collection.updated_at = utcnow()


def _participant_rows(session: Session, collection: Collection) -> list[dict]:
    participants = list(
        session.scalars(select(CollectionParticipant).where(CollectionParticipant.collection_id == collection.id))
    )
    rows = []
    for participant in participants:
        employee = session.get(Employee, participant.employee_id)
        rows.append(
            {
                "id": str(participant.id),
                "employee_id": str(participant.employee_id),
                "preferred_name": employee.preferred_name if employee else "",
                "full_name": employee.full_name if employee else "",
                "status": participant.status,
                "amount": _money_str(participant.amount),
                "delivery_status": participant.delivery_status,
                "bot_status": employee.bot_status if employee else None,
            }
        )
    return rows


def _collection_dict(collection: Collection) -> dict:
    return {
        "id": str(collection.id),
        "employee_id": str(collection.employee_id),
        "title": collection.title,
        "description": collection.description,
        "contribution_mode": collection.contribution_mode,
        "fixed_amount": _money_str(collection.fixed_amount),
        "currency": collection.currency,
        "deadline": collection.deadline.isoformat() if collection.deadline else None,
        "status": collection.status,
        "scope": collection.scope,
        "payment_details": collection.payment_details,
        "opened_at": _iso(collection.opened_at),
        "closed_at": _iso(collection.closed_at),
    }


def _employee_dict(employee: Employee) -> dict:
    return {
        "id": str(employee.id),
        "status": employee.status,
        "department_id": str(employee.department_id) if employee.department_id else None,
        "participate_in_collections": employee.participate_in_collections,
        "bot_status": employee.bot_status,
        "telegram_id": employee.telegram_id,
        "notification_settings": employee.notification_settings or {},
    }


def _birthday_employee(session: Session, employee_id: UUID) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Сотрудник не найден")
    return employee


def _get(session: Session, collection_id: UUID) -> Collection:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError("Сбор не найден")
    return collection


def _open_collection(session: Session, collection_id: UUID) -> Collection:
    collection = _get(session, collection_id)
    if collection.status != "open":
        raise DomainError("Сбор сейчас не принимает ответы")
    return collection


def _participant(session: Session, collection_id: UUID, employee_id: UUID) -> CollectionParticipant:
    participant = session.scalar(
        select(CollectionParticipant).where(
            CollectionParticipant.collection_id == collection_id,
            CollectionParticipant.employee_id == employee_id,
        )
    )
    if participant is None:
        raise DomainError("Вы не в списке участников этого сбора")
    return participant


def _mode(mode: str, amount: Decimal | None) -> str:
    if mode not in {"fixed", "arbitrary"}:
        raise DomainError("Тип взноса: фиксированный или произвольный")
    if mode == "fixed" and (amount is None or amount <= 0):
        raise DomainError("Для фиксированного взноса укажите сумму")
    return mode


def _scope(scope: dict | None) -> dict:
    raw = scope or {"all": True}
    return {
        "all": bool(raw.get("all")),
        "department_ids": [str(item) for item in raw.get("department_ids") or []],
        "employee_ids": [str(item) for item in raw.get("employee_ids") or []],
    }


def _permanent_status(code: str) -> str:
    if code == "blocked":
        return "blocked"
    if code == "not_started":
        return "not_started"
    return "failed"


def _money_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()
