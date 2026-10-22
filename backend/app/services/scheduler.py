"""DB-backed worker step. Cancelled actions are skipped. Sends are idempotent."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScheduledAction, utcnow
from app.services.announcements import dispatch_announcement
from app.services.greetings import scan_birthdays, send_greeting


def run_due(session: Session, sender, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    scan = scan_birthdays(session, sender=sender, now=now)
    actions = list(
        session.scalars(
            select(ScheduledAction)
            .where(ScheduledAction.status == "pending", ScheduledAction.run_at <= now)
            .order_by(ScheduledAction.run_at)
            .with_for_update(skip_locked=True)
        )
    )
    done = 0
    for action in actions:
        if action.status != "pending":
            continue
        if action.kind == "greeting_send" and action.entity_id:
            greeting = send_greeting(session, action.entity_id, sender, now=now)
            if greeting.status != "scheduled":
                _finish(action, now)
                done += 1
        elif action.kind == "announcement_send" and action.entity_id:
            announcement = dispatch_announcement(session, action.entity_id, sender, now=now)
            if announcement.status in {"sent", "cancelled"}:
                _finish(action, now)
                done += 1
        else:
            _finish(action, now)
        session.commit()
    return {"scan": scan, "actions_finished": done}


def cancel_action(session: Session, action_id: UUID, actor_id: UUID | None) -> ScheduledAction:
    from app.errors import DomainError, NotFoundError
    from app.services.announcements import cancel_announcement
    from app.services.audit import write_audit
    from app.services.greetings import cancel_greeting

    action = session.get(ScheduledAction, action_id, with_for_update=True)
    if action is None:
        raise NotFoundError("Задача не найдена")
    if action.status != "pending":
        raise DomainError("Эту задачу уже нельзя отменить")
    action.status = "cancelled"
    action.cancelled_at = utcnow()
    if action.kind == "greeting_send" and action.entity_id:
        cancel_greeting(session, action.entity_id, actor_id)
    elif action.kind == "announcement_send" and action.entity_id:
        cancel_announcement(session, action.entity_id, actor_id)
    else:
        write_audit(session, actor_id, "schedule.cancel", "scheduled_action", action.id, {})
        session.commit()
    return action


def _finish(action: ScheduledAction, now: datetime) -> None:
    action.status = "done"
    action.finished_at = now
