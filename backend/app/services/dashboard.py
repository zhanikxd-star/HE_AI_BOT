"""Dashboard and calendar read models for HR."""

from __future__ import annotations

import calendar
from datetime import datetime, timezone

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.domain.rules import days_until_birthday, occasion_on_or_after, org_local_date
from app.models import Announcement, Collection, Employee, Greeting, HrBirthdayNotice
from app.services.org import get_org


def dashboard(session: Session, now: datetime | None = None) -> dict:
    org = get_org(session)
    now = now or datetime.now(timezone.utc)
    today = org_local_date(now, org.timezone)
    upcoming = []
    for employee in session.scalars(select(Employee).where(Employee.status == "active")):
        days = days_until_birthday(employee.birth_date, today)
        if days > 14:
            continue
        occasion = occasion_on_or_after(employee.birth_date, today)
        greeting = session.scalar(
            select(Greeting).where(Greeting.employee_id == employee.id, Greeting.occasion_date == occasion)
        )
        upcoming.append(
            {
                "employee_id": str(employee.id),
                "preferred_name": employee.preferred_name,
                "full_name": employee.full_name,
                "occasion_date": occasion.isoformat(),
                "days_until": days,
                "public_greeting_consent": employee.public_greeting_consent,
                "bot_status": employee.bot_status,
                "greeting_status": greeting.status if greeting else None,
                "greeting_id": str(greeting.id) if greeting else None,
            }
        )
    upcoming.sort(key=lambda item: item["days_until"])
    notices = []
    for notice in session.scalars(select(HrBirthdayNotice).where(HrBirthdayNotice.occasion_date >= today)):
        employee = session.get(Employee, notice.employee_id)
        notices.append(
            {
                "id": str(notice.id),
                "employee_id": str(notice.employee_id),
                "preferred_name": employee.preferred_name if employee else "",
                "occasion_date": notice.occasion_date.isoformat(),
            }
        )
    collections = [
        {"id": str(item.id), "title": item.title, "status": item.status, "deadline": item.deadline.isoformat() if item.deadline else None}
        for item in session.scalars(select(Collection).where(Collection.status == "open"))
    ]
    announcements = [
        {
            "id": str(item.id),
            "title": item.title,
            "status": item.status,
            "scheduled_for": item.scheduled_for.isoformat() if item.scheduled_for else None,
        }
        for item in session.scalars(select(Announcement).where(Announcement.status == "scheduled"))
    ]
    active = list(session.scalars(select(Employee).where(Employee.status == "active")))
    return {
        "today": today.isoformat(),
        "timezone": org.timezone,
        "upcoming_birthdays": upcoming,
        "notices": notices,
        "active_collections": collections,
        "scheduled_announcements": announcements,
        "bot_attention": {
            "not_started": sum(1 for item in active if item.bot_status == "not_started"),
            "blocked": sum(1 for item in active if item.bot_status == "blocked"),
        },
    }


def month_calendar(session: Session, year: int, month: int) -> dict:
    get_org(session)
    employees = list(session.scalars(select(Employee).where(extract("month", Employee.birth_date) == month)))
    days = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        matched = []
        for employee in employees:
            birth_day = employee.birth_date.day
            if employee.birth_date.month == 2 and employee.birth_date.day == 29 and not calendar.isleap(year):
                birth_day = 28
            if birth_day != day:
                continue
            matched.append(
                {
                    "employee_id": str(employee.id),
                    "preferred_name": employee.preferred_name,
                    "full_name": employee.full_name,
                    "status": employee.status,
                    "public_greeting_consent": employee.public_greeting_consent,
                    "bot_status": employee.bot_status,
                }
            )
        if matched:
            days.append({"date": f"{year:04d}-{month:02d}-{day:02d}", "birthdays": matched})
    return {"year": year, "month": month, "days": days}
