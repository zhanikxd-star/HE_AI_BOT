from datetime import date, datetime, timedelta, timezone

import pytest

from app.adapters.telegram import FakeTelegramSender
from app.errors import DomainError
from app.models import Greeting, Organization
from app.services.employees import EmployeeInput, create_employee, set_own_consent
from app.services.greetings import approve_greeting, cancel_greeting, scan_birthdays
from app.services.scheduler import run_due
from sqlalchemy import select


TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)


def _person(db, *, consent: bool, name="Аружан Сериккызы", preferred="Аружан"):
    return create_employee(
        db,
        EmployeeInput(
            full_name=name,
            preferred_name=preferred,
            birth_date=date(1994, TODAY.month, TODAY.day),
            public_greeting_consent=consent,
            position="аналитик",
        ),
        None,
    )


def test_greeting_requires_consent_and_is_not_sent(db):
    sender = FakeTelegramSender()
    _person(db, consent=False)
    scan_birthdays(db, today=TODAY, sender=sender, now=NOW)
    greeting = db.scalar(select(Greeting))
    assert greeting.status == "skipped_no_consent"
    with pytest.raises(DomainError):
        approve_greeting(db, greeting.id, None, "С днём рождения!", NOW)
    run_due(db, sender, now=NOW)
    assert sender.calls == []


def test_greeting_sends_once_after_approval_and_rerun(db):
    sender = FakeTelegramSender()
    org = db.scalar(select(Organization))
    org.corporate_chat_id = -100555
    db.commit()
    employee = _person(db, consent=True)
    scan_birthdays(db, today=TODAY, sender=sender, now=NOW)
    greeting = db.scalar(select(Greeting).where(Greeting.employee_id == employee.id))
    assert greeting.status == "pending_approval"
    approve_greeting(db, greeting.id, None, "Аружан, с днём рождения!", NOW - timedelta(minutes=1))
    run_due(db, sender, now=NOW)
    run_due(db, sender, now=NOW)
    db.refresh(greeting)
    assert greeting.status == "sent"
    assert len(sender.calls) == 1
    assert sender.calls[0]["chat_id"] == -100555


def test_employee_can_revoke_consent_and_stop_a_scheduled_greeting(db):
    sender = FakeTelegramSender()
    employee = _person(db, consent=True)
    set_own_consent(db, employee.id, False)
    db.refresh(employee)
    assert employee.public_greeting_consent is False
    scan_birthdays(db, today=TODAY, sender=sender, now=NOW)
    greeting = db.scalar(select(Greeting))
    assert greeting.status == "skipped_no_consent"
    assert sender.calls == []


def test_scheduled_greeting_can_be_cancelled(db):
    sender = FakeTelegramSender()
    employee = _person(db, consent=True)
    scan_birthdays(db, today=TODAY, sender=sender, now=NOW)
    greeting = db.scalar(select(Greeting).where(Greeting.employee_id == employee.id))
    approve_greeting(db, greeting.id, None, "Текст", NOW + timedelta(days=1))
    cancel_greeting(db, greeting.id, None)
    run_due(db, sender, now=NOW + timedelta(days=2))
    db.refresh(greeting)
    assert greeting.status == "cancelled"
    assert sender.calls == []


def test_restart_while_sending_does_not_send_again(db):
    sender = FakeTelegramSender()
    employee = _person(db, consent=True)
    scan_birthdays(db, today=TODAY, sender=sender, now=NOW)
    greeting = db.scalar(select(Greeting).where(Greeting.employee_id == employee.id))
    approve_greeting(db, greeting.id, None, "Текст", NOW - timedelta(minutes=1))
    greeting.status = "sending"
    db.commit()
    run_due(db, sender, now=NOW)
    assert sender.calls == []
