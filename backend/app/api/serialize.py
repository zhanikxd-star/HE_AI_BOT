"""JSON helpers for API responses."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, Employee


def iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def department_map(session: Session) -> dict:
    return {row.id: row.name for row in session.scalars(select(Department))}


def employee_json(employee: Employee, names: dict | None = None) -> dict:
    names = names or {}
    return {
        "id": str(employee.id),
        "full_name": employee.full_name,
        "preferred_name": employee.preferred_name,
        "birth_date": employee.birth_date.isoformat(),
        "department_id": str(employee.department_id) if employee.department_id else None,
        "department_name": names.get(employee.department_id),
        "position": employee.position,
        "phone": employee.phone,
        "city": employee.city,
        "telegram_id": employee.telegram_id,
        "telegram_username": employee.telegram_username,
        "hired_at": iso(employee.hired_at),
        "status": employee.status,
        "public_greeting_consent": employee.public_greeting_consent,
        "notification_settings": employee.notification_settings,
        "participate_in_collections": employee.participate_in_collections,
        "bot_status": employee.bot_status,
        "invite_token": employee.invite_token,
    }


def money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"
