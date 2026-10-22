"""Audit log for administrator actions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog, utcnow


def write_audit(
    session: Session,
    actor_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: object,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            payload=payload or {},
            created_at=utcnow(),
        )
    )
