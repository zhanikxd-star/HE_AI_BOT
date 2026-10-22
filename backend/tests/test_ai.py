import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.adapters.llm import TestLlmAdapter
from app.adapters.telegram import FakeTelegramSender
from app.models import Collection, CollectionParticipant, Greeting
from app.services.ai import approve_draft, create_draft
from app.services.employees import EmployeeInput, create_employee
from app.services.org import PAYMENT_FIXED_AMOUNT, PAYMENT_PHONE, payment_details_text
from app.services.scheduler import run_due


def test_ai_draft_does_not_send_or_open_collection(db):
    sender = FakeTelegramSender()
    employee = create_employee(
        db,
        EmployeeInput(
            full_name="Аружан Сериккызы",
            preferred_name="Аружан",
            birth_date=date(1995, 5, 5),
            telegram_id=555,
            public_greeting_consent=True,
            position="аналитик",
        ),
        None,
    )
    draft = create_draft(
        db,
        task="nl_command",
        actor_id=None,
        llm=TestLlmAdapter(),
        model_name="test",
        instruction="Поздравь завтра Аружан с днём рождения и подготовь сбор на подарок на 25 000 тенге",
    )
    assert db.scalar(select(func.count()).select_from(Collection)) == 0
    assert db.scalar(select(func.count()).select_from(Greeting)) == 0
    blob = json.dumps(draft.request_fields, ensure_ascii=False)
    assert "telegram_id" not in blob
    assert "555" not in blob
    assert "instruction" in draft.response["received_fields"]
    assert "candidate_names" in draft.response["received_fields"]
    approved = approve_draft(db, draft.id, None)
    collection = db.get(Collection, approved.collection_id)
    greeting = db.get(Greeting, approved.greeting_id)
    assert collection.status == "draft"
    assert collection.contribution_mode == "fixed"
    assert collection.fixed_amount == PAYMENT_FIXED_AMOUNT
    assert collection.payment_details == payment_details_text(PAYMENT_PHONE)
    assert Decimal("25000") != collection.fixed_amount
    assert greeting.status == "pending_approval"
    assert db.scalar(select(func.count()).select_from(CollectionParticipant)) == 0
    run_due(db, sender)
    assert sender.calls == []
    assert employee.telegram_id == 555


def test_greeting_draft_records_only_allowed_fields(db):
    employee = create_employee(
        db,
        EmployeeInput(
            full_name="Аружан Сериккызы",
            preferred_name="Аружан",
            birth_date=date(1995, 5, 5),
            telegram_id=777,
            telegram_username="secret_user",
        ),
        None,
    )
    draft = create_draft(
        db,
        task="greeting",
        actor_id=None,
        llm=TestLlmAdapter(),
        model_name="test",
        employee_id=employee.id,
        style="warm",
    )
    assert set(draft.request_fields) <= {"preferred_name", "position", "department", "style", "variant"}
    assert "777" not in json.dumps(draft.request_fields)
    approve_draft(db, draft.id, None)
    greeting = db.scalar(select(Greeting))
    assert greeting.status in {"pending_approval", "skipped_no_consent"}
    assert greeting.status != "sent"
