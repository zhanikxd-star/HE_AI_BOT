"""Birthday scan, approval, cancellation, and at-most-once public greetings."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.rules import (
    NO_RESEND,
    days_until_birthday,
    default_greeting_send_at,
    occasion_on_or_after,
    org_local_date,
)
from app.errors import DomainError, NotFoundError
from app.models import Employee, Greeting, HrBirthdayNotice, ScheduledAction, User, utcnow
from app.ports import PermanentDeliveryError, TransientTelegramError
from app.services.audit import write_audit
from app.services.org import get_org

logger = logging.getLogger(__name__)


def scan_birthdays(session: Session, *, today: date | None = None, sender=None, now: datetime | None = None) -> dict:
    org = get_org(session)
    now = now or datetime.now(timezone.utc)
    if today is None:
        today = org_local_date(now, org.timezone)
    created_notices = 0
    created_greetings = 0
    employees = list(session.scalars(select(Employee).where(Employee.status == "active")))
    for employee in employees:
        days = days_until_birthday(employee.birth_date, today)
        occasion = occasion_on_or_after(employee.birth_date, today)
        if 0 < days <= org.greeting_lead_days and _ensure_notice(session, employee, occasion, sender):
            created_notices += 1
        if days == 0 and _ensure_greeting(session, employee, occasion):
            created_greetings += 1
    session.commit()
    return {"today": today.isoformat(), "notices_created": created_notices, "greetings_created": created_greetings}


def approve_greeting(
    session: Session,
    greeting_id: UUID,
    actor_id: UUID | None,
    text: str,
    scheduled_for: datetime | None = None,
) -> Greeting:
    greeting = _get(session, greeting_id)
    if greeting.status in {"sent", "simulated", "sending"}:
        raise DomainError("Поздравление уже отправляется или отправлено")
    employee = session.get(Employee, greeting.employee_id)
    if employee is None or not employee.public_greeting_consent:
        greeting.status = "skipped_no_consent"
        greeting.updated_at = utcnow()
        _cancel_actions(session, greeting.id)
        session.commit()
        raise DomainError("Нет согласия на публичное поздравление")
    if employee.status != "active":
        raise DomainError("Сотрудник неактивен")
    cleaned = (text or "").strip()
    if not cleaned:
        raise DomainError("Нужен текст поздравления")
    org = get_org(session)
    when = scheduled_for or default_greeting_send_at(greeting.occasion_date, org.timezone, org.greeting_hour)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    greeting.text = cleaned
    greeting.status = "scheduled"
    greeting.scheduled_for = when
    greeting.failure_reason = None
    greeting.updated_at = utcnow()
    _upsert_action(
        session,
        kind="greeting_send",
        run_at=when,
        key=f"greeting-send:{greeting.id}",
        entity_type="greeting",
        entity_id=greeting.id,
    )
    write_audit(session, actor_id, "greeting.approve", "greeting", greeting.id, {})
    session.commit()
    return greeting


def cancel_greeting(session: Session, greeting_id: UUID, actor_id: UUID | None) -> Greeting:
    greeting = _get(session, greeting_id)
    if greeting.status in {"sent", "simulated", "sending"}:
        raise DomainError("Отправка уже началась, отменить нельзя")
    greeting.status = "cancelled"
    greeting.updated_at = utcnow()
    _cancel_actions(session, greeting.id)
    write_audit(session, actor_id, "greeting.cancel", "greeting", greeting.id, {})
    session.commit()
    return greeting


def send_greeting(session: Session, greeting_id: UUID, sender, now: datetime | None = None) -> Greeting:
    """Send once. A restart sees sending/sent/simulated and does not send again."""
    now = now or datetime.now(timezone.utc)
    greeting = session.get(Greeting, greeting_id, with_for_update=True)
    if greeting is None:
        raise NotFoundError("Поздравление не найдено")
    if greeting.status in NO_RESEND or greeting.status == "failed":
        return greeting
    if greeting.status != "scheduled":
        return greeting
    employee = session.get(Employee, greeting.employee_id)
    if employee is None or employee.status != "active" or not employee.public_greeting_consent:
        greeting.status = "skipped_no_consent"
        greeting.updated_at = utcnow()
        session.commit()
        return greeting
    if greeting.scheduled_for and greeting.scheduled_for > now:
        return greeting
    if not greeting.text.strip():
        return greeting
    org = get_org(session)
    if not org.corporate_chat_id:
        greeting.status = "failed"
        greeting.failure_reason = "no_corporate_chat"
        greeting.updated_at = utcnow()
        session.commit()
        return greeting
    greeting.status = "sending"
    greeting.updated_at = utcnow()
    session.commit()
    try:
        result = sender.send_message(int(org.corporate_chat_id), greeting.text)
    except TransientTelegramError:
        greeting.status = "failed"
        greeting.failure_reason = "transient"
        greeting.updated_at = utcnow()
        session.commit()
        logger.exception("greeting send failed", extra={"event": "greeting_send", "entity_id": str(greeting.id)})
        return greeting
    except PermanentDeliveryError as exc:
        greeting.status = "failed"
        greeting.failure_reason = exc.code
        greeting.updated_at = utcnow()
        session.commit()
        return greeting
    greeting.status = "simulated" if result.simulated or result.provider == "test" else "sent"
    greeting.provider = result.provider
    greeting.telegram_message_id = result.message_id
    greeting.sent_at = now
    greeting.updated_at = utcnow()
    session.commit()
    return greeting


def list_greetings(session: Session, status: str | None = None) -> list[Greeting]:
    stmt = select(Greeting).order_by(Greeting.occasion_date.desc())
    if status:
        stmt = stmt.where(Greeting.status == status)
    return list(session.scalars(stmt))


def get_greeting(session: Session, greeting_id: UUID) -> Greeting:
    return _get(session, greeting_id)


def _ensure_notice(session: Session, employee: Employee, occasion: date, sender) -> bool:
    existing = session.scalar(
        select(HrBirthdayNotice).where(
            HrBirthdayNotice.employee_id == employee.id,
            HrBirthdayNotice.occasion_date == occasion,
        )
    )
    if existing is not None:
        return False
    notice = HrBirthdayNotice(employee_id=employee.id, occasion_date=occasion, alerts_sent=False, created_at=utcnow())
    session.add(notice)
    session.flush()
    if sender is not None:
        _notify_hr(session, employee, occasion, sender)
        notice.alerts_sent = True
    return True


def _notify_hr(session: Session, employee: Employee, occasion: date, sender) -> None:
    admins = list(session.scalars(select(User).where(User.is_active.is_(True), User.telegram_id.is_not(None))))
    text = (
        f"Через несколько дней день рождения: {employee.preferred_name} ({occasion.isoformat()}). "
        "Можно открыть добровольный сбор. Публичное поздравление уйдёт только после вашего утверждения и согласия сотрудника."
    )
    for admin in admins:
        if not admin.telegram_id:
            continue
        try:
            sender.send_message(int(admin.telegram_id), text)
        except (TransientTelegramError, PermanentDeliveryError):
            logger.warning("hr birthday alert was not delivered", extra={"event": "hr_notice", "entity_id": str(employee.id)})


def _ensure_greeting(session: Session, employee: Employee, occasion: date) -> bool:
    existing = session.scalar(
        select(Greeting).where(Greeting.employee_id == employee.id, Greeting.occasion_date == occasion)
    )
    if existing is not None:
        if existing.status in {"sent", "simulated", "sending", "cancelled", "failed"}:
            return False
        if not employee.public_greeting_consent and existing.status in {"pending_approval", "scheduled", "draft"}:
            existing.status = "skipped_no_consent"
            existing.updated_at = utcnow()
            _cancel_actions(session, existing.id)
        elif employee.public_greeting_consent and existing.status == "skipped_no_consent":
            existing.status = "pending_approval"
            existing.updated_at = utcnow()
        return False
    status = "pending_approval" if employee.public_greeting_consent else "skipped_no_consent"
    session.add(
        Greeting(
            employee_id=employee.id,
            occasion_date=occasion,
            status=status,
            text="",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    return True


def _get(session: Session, greeting_id: UUID) -> Greeting:
    greeting = session.get(Greeting, greeting_id)
    if greeting is None:
        raise NotFoundError("Поздравление не найдено")
    return greeting


def _cancel_actions(session: Session, greeting_id: UUID) -> None:
    actions = session.scalars(
        select(ScheduledAction).where(
            ScheduledAction.entity_type == "greeting",
            ScheduledAction.entity_id == greeting_id,
            ScheduledAction.status == "pending",
        )
    )
    for action in actions:
        action.status = "cancelled"
        action.cancelled_at = utcnow()


def _upsert_action(session: Session, *, kind: str, run_at: datetime, key: str, entity_type: str, entity_id: UUID) -> None:
    action = session.scalar(select(ScheduledAction).where(ScheduledAction.idempotency_key == key))
    if action is None:
        session.add(
            ScheduledAction(
                kind=kind,
                run_at=run_at,
                status="pending",
                idempotency_key=key,
                entity_type=entity_type,
                entity_id=entity_id,
                payload={},
                created_at=utcnow(),
            )
        )
        return
    action.status = "pending"
    action.run_at = run_at
    action.cancelled_at = None
    action.finished_at = None
