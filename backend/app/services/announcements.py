"""Personal announcements: segment, schedule, RSVP, at-most-once delivery."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rules import announcement_stats, in_segment, initial_delivery_status
from app.errors import DomainError, NotFoundError
from app.models import Announcement, AnnouncementDelivery, Employee, ScheduledAction, utcnow
from app.ports import Button, PermanentDeliveryError, TransientTelegramError
from app.services.audit import write_audit

ANNOUNCEMENT_TYPES = {"event", "meeting", "news", "schedule", "training", "survey", "reminder"}


def create_announcement(
    session: Session,
    *,
    title: str,
    body: str,
    type: str,
    segment: dict | None,
    requires_rsvp: bool,
    image_url: str | None,
    document_url: str | None,
    actor_id: UUID | None,
) -> Announcement:
    if type not in ANNOUNCEMENT_TYPES:
        raise DomainError("Неизвестный тип объявления")
    announcement = Announcement(
        title=title.strip(),
        body=(body or "").strip(),
        type=type,
        image_url=image_url or None,
        document_url=document_url or None,
        status="draft",
        requires_rsvp=requires_rsvp,
        segment=_segment(segment),
        created_by=actor_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    if not announcement.title:
        raise DomainError("Укажите заголовок")
    session.add(announcement)
    write_audit(session, actor_id, "announcement.create", "announcement", announcement.id, {"type": type})
    session.commit()
    return announcement


def update_announcement(session: Session, announcement_id: UUID, changes: dict, actor_id: UUID | None) -> Announcement:
    announcement = _get(session, announcement_id)
    if announcement.status != "draft":
        raise DomainError("Редактировать можно только черновик")
    if "title" in changes and changes["title"]:
        announcement.title = str(changes["title"]).strip()
    if "body" in changes and changes["body"] is not None:
        announcement.body = str(changes["body"]).strip()
    if "type" in changes and changes["type"]:
        if changes["type"] not in ANNOUNCEMENT_TYPES:
            raise DomainError("Неизвестный тип объявления")
        announcement.type = changes["type"]
    if "segment" in changes and changes["segment"] is not None:
        announcement.segment = _segment(changes["segment"])
    if "requires_rsvp" in changes and changes["requires_rsvp"] is not None:
        announcement.requires_rsvp = bool(changes["requires_rsvp"])
    if "image_url" in changes:
        announcement.image_url = changes["image_url"] or None
    if "document_url" in changes:
        announcement.document_url = changes["document_url"] or None
    announcement.updated_at = utcnow()
    write_audit(session, actor_id, "announcement.update", "announcement", announcement.id, {})
    session.commit()
    return announcement


def preview(session: Session, announcement_id: UUID) -> list[dict]:
    announcement = _get(session, announcement_id)
    rows = []
    for employee in _recipients(session, announcement.segment):
        payload = _employee_dict(employee)
        rows.append(
            {
                "employee_id": str(employee.id),
                "preferred_name": employee.preferred_name,
                "full_name": employee.full_name,
                "bot_status": employee.bot_status,
                "delivery_status": initial_delivery_status(payload, "announcements"),
            }
        )
    return rows


def schedule_announcement(
    session: Session,
    announcement_id: UUID,
    when: datetime,
    actor_id: UUID | None,
) -> Announcement:
    announcement = _get(session, announcement_id)
    if announcement.status != "draft":
        raise DomainError("Запланировать можно только черновик")
    if not announcement.body.strip():
        raise DomainError("Нужен текст объявления")
    if not _recipients(session, announcement.segment):
        raise DomainError("В сегменте никого нет")
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    announcement.status = "scheduled"
    announcement.scheduled_for = when
    announcement.updated_at = utcnow()
    _upsert_action(session, announcement.id, when)
    write_audit(session, actor_id, "announcement.schedule", "announcement", announcement.id, {})
    session.commit()
    return announcement


def cancel_announcement(session: Session, announcement_id: UUID, actor_id: UUID | None) -> Announcement:
    announcement = _get(session, announcement_id)
    if announcement.status in {"sent", "sending"}:
        raise DomainError("Рассылка уже началась")
    announcement.status = "cancelled"
    announcement.updated_at = utcnow()
    actions = session.scalars(
        select(ScheduledAction).where(
            ScheduledAction.entity_type == "announcement",
            ScheduledAction.entity_id == announcement.id,
            ScheduledAction.status == "pending",
        )
    )
    now = utcnow()
    for action in actions:
        action.status = "cancelled"
        action.cancelled_at = now
    write_audit(session, actor_id, "announcement.cancel", "announcement", announcement.id, {})
    session.commit()
    return announcement


def dispatch_announcement(session: Session, announcement_id: UUID, sender, now: datetime | None = None) -> Announcement:
    now = now or datetime.now(timezone.utc)
    announcement = session.get(Announcement, announcement_id, with_for_update=True)
    if announcement is None:
        raise NotFoundError("Объявление не найдено")
    if announcement.status in {"cancelled", "draft", "sent"}:
        return announcement
    if announcement.status == "scheduled" and announcement.scheduled_for and announcement.scheduled_for > now:
        return announcement
    announcement.status = "sending"
    announcement.updated_at = utcnow()
    session.commit()
    _ensure_deliveries(session, announcement)
    deliveries = list(
        session.scalars(select(AnnouncementDelivery).where(AnnouncementDelivery.announcement_id == announcement.id))
    )
    for delivery in deliveries:
        _send_one(session, announcement, delivery, sender, now)
    pending = [
        item
        for item in session.scalars(
            select(AnnouncementDelivery).where(AnnouncementDelivery.announcement_id == announcement.id)
        )
        if item.delivery_status == "pending"
    ]
    announcement.status = "sending" if pending else "sent"
    announcement.updated_at = utcnow()
    session.commit()
    return announcement


def set_rsvp(session: Session, announcement_id: UUID, employee_id: UUID, rsvp: str) -> AnnouncementDelivery:
    if rsvp not in {"will_attend", "cannot_attend"}:
        raise DomainError("Ответ: буду или не смогу")
    announcement = _get(session, announcement_id)
    if not announcement.requires_rsvp:
        raise DomainError("Для этого объявления подтверждение не нужно")
    delivery = session.scalar(
        select(AnnouncementDelivery).where(
            AnnouncementDelivery.announcement_id == announcement.id,
            AnnouncementDelivery.employee_id == employee_id,
        )
    )
    if delivery is None:
        raise NotFoundError("Приглашение не найдено")
    if delivery.delivery_status not in {"sent", "simulated"}:
        raise DomainError("Объявление не доставлено, ответ не записан")
    delivery.rsvp_status = rsvp
    session.commit()
    return delivery


def stats(session: Session, announcement_id: UUID) -> dict:
    announcement = _get(session, announcement_id)
    deliveries = list(
        session.scalars(select(AnnouncementDelivery).where(AnnouncementDelivery.announcement_id == announcement.id))
    )
    payload = announcement_stats(
        [{"delivery_status": item.delivery_status, "rsvp_status": item.rsvp_status} for item in deliveries]
    )
    payload["status"] = announcement.status
    payload["rows"] = [_delivery_json(session, item) for item in deliveries]
    return payload


def list_announcements(session: Session) -> list[Announcement]:
    return list(session.scalars(select(Announcement).order_by(Announcement.created_at.desc())))


def get_announcement(session: Session, announcement_id: UUID) -> Announcement:
    return _get(session, announcement_id)


def _send_one(session: Session, announcement: Announcement, delivery: AnnouncementDelivery, sender, now: datetime) -> None:
    if delivery.delivery_status != "pending":
        return
    employee = session.get(Employee, delivery.employee_id)
    if employee is None or not employee.telegram_id:
        delivery.delivery_status = "not_started"
        session.commit()
        return
    delivery.delivery_status = "sending"
    session.commit()
    buttons = None
    if announcement.requires_rsvp:
        buttons = [[
            Button("Буду", f"r:y:{announcement.id}"),
            Button("Не смогу", f"r:n:{announcement.id}"),
        ]]
    text = f"{announcement.title}\n\n{announcement.body}"
    try:
        result = sender.send_message(
            int(employee.telegram_id),
            text,
            buttons=buttons,
            image_url=announcement.image_url,
            document_url=announcement.document_url,
        )
    except TransientTelegramError:
        delivery.delivery_status = "failed"
        session.commit()
        return
    except PermanentDeliveryError as exc:
        delivery.delivery_status = "blocked" if exc.code == "blocked" else "not_started" if exc.code == "not_started" else "failed"
        if exc.code == "blocked":
            employee.bot_status = "blocked"
            employee.updated_at = utcnow()
        session.commit()
        return
    if result.simulated or result.provider == "test":
        delivery.delivery_status = "simulated"
    else:
        delivery.delivery_status = "sent"
        delivery.sent_at = now
    delivery.provider = result.provider
    delivery.telegram_message_id = result.message_id
    session.commit()


def _ensure_deliveries(session: Session, announcement: Announcement) -> None:
    existing = {
        item.employee_id
        for item in session.scalars(
            select(AnnouncementDelivery).where(AnnouncementDelivery.announcement_id == announcement.id)
        )
    }
    for employee in _recipients(session, announcement.segment):
        if employee.id in existing:
            continue
        session.add(
            AnnouncementDelivery(
                announcement_id=announcement.id,
                employee_id=employee.id,
                delivery_status=initial_delivery_status(_employee_dict(employee), "announcements"),
                rsvp_status="none",
            )
        )
    session.commit()


def _recipients(session: Session, segment: dict) -> list[Employee]:
    employees = list(session.scalars(select(Employee)))
    return [employee for employee in employees if in_segment(_employee_dict(employee), segment)]


def _employee_dict(employee: Employee) -> dict:
    return {
        "id": str(employee.id),
        "status": employee.status,
        "department_id": str(employee.department_id) if employee.department_id else None,
        "bot_status": employee.bot_status,
        "telegram_id": employee.telegram_id,
        "notification_settings": employee.notification_settings or {},
    }


def _segment(segment: dict | None) -> dict:
    raw = segment or {"all": True}
    return {
        "all": bool(raw.get("all")),
        "department_ids": [str(item) for item in raw.get("department_ids") or []],
        "employee_ids": [str(item) for item in raw.get("employee_ids") or []],
    }


def _upsert_action(session: Session, announcement_id: UUID, when: datetime) -> None:
    key = f"announcement-send:{announcement_id}"
    action = session.scalar(select(ScheduledAction).where(ScheduledAction.idempotency_key == key))
    if action is None:
        session.add(
            ScheduledAction(
                kind="announcement_send",
                run_at=when,
                status="pending",
                idempotency_key=key,
                entity_type="announcement",
                entity_id=announcement_id,
                payload={},
                created_at=utcnow(),
            )
        )
        return
    action.status = "pending"
    action.run_at = when
    action.cancelled_at = None
    action.finished_at = None


def _get(session: Session, announcement_id: UUID) -> Announcement:
    announcement = session.get(Announcement, announcement_id)
    if announcement is None:
        raise NotFoundError("Объявление не найдено")
    return announcement


def _delivery_json(session: Session, delivery: AnnouncementDelivery) -> dict:
    employee = session.get(Employee, delivery.employee_id)
    return {
        "employee_id": str(delivery.employee_id),
        "preferred_name": employee.preferred_name if employee else "",
        "full_name": employee.full_name if employee else "",
        "bot_status": employee.bot_status if employee else None,
        "delivery_status": delivery.delivery_status,
        "rsvp_status": delivery.rsvp_status,
    }
