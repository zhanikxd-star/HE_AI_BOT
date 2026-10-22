from sqlalchemy import func, select

from app.adapters.notion import live_create_page, notion_fields
from app.models import Department, Employee, OnboardingApplication
from app.services.onboarding import answer, choose_existing, choose_sales, set_consent
from app.services.org import NOTION_DATABASE_ID, SALES_DEPARTMENT


def test_notion_payload_drops_extra_hr_fields():
    payload = notion_fields(
        {
            "full_name": "Айгерим Сатова",
            "preferred_name": "Айгерим",
            "phone": "+77010000000",
            "birth_date": "1994-04-04",
            "position": "менеджер",
            "hired_at": "2026-11-02",
            "city": "Алматы",
            "telegram_id": 900,
            "telegram_username": "aigerim",
            "completed_at": "2026-10-22T00:00:00+00:00",
            "public_greeting_consent": True,
            "invite_token": "secret-token",
        }
    )
    assert "public_greeting_consent" not in payload
    assert "invite_token" not in payload
    assert set(payload) == {
        "full_name",
        "preferred_name",
        "phone",
        "birth_date",
        "position",
        "hired_at",
        "city",
        "telegram_id",
        "telegram_username",
        "completed_at",
    }


def test_sales_onboarding_saves_locally_and_skips_notion(db, monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("notion was called")

    monkeypatch.setattr("app.services.onboarding.live_create_page", fail_if_called)
    assert live_create_page is not None
    choose_existing(db, 4242)
    assert db.scalar(select(func.count()).select_from(Employee)) == 0
    reply = choose_sales(db, 4242, "new_sales")
    assert "ФИО" in reply.text
    steps = [
        ("Айгерим Сатова", "обращаться"),
        ("Айгерим", "телефона"),
        ("+77010000000", "рождения"),
        ("04.04.1994", "должность"),
        ("менеджер", "выхода"),
        ("02.11.2026", "городе"),
        ("Алматы", "поздравлять"),
    ]
    for text, marker in steps:
        reply = answer(db, 4242, "new_sales", text)
        assert marker in reply.text.lower()
    done = set_consent(db, 4242, "new_sales", False)
    assert "не загружены" in done.text
    assert done.documents == []
    employee = db.scalar(select(Employee).where(Employee.telegram_id == 4242))
    department = db.get(Department, employee.department_id)
    application = db.scalar(select(OnboardingApplication).where(OnboardingApplication.telegram_id == 4242))
    assert employee.full_name == "Айгерим Сатова"
    assert employee.status == "active"
    assert employee.public_greeting_consent is False
    assert employee.city == "Алматы"
    assert department.name == SALES_DEPARTMENT
    assert application.status == "completed"
    assert application.notion_status == "skipped"
    assert application.notion_error == "missing_key"
    assert db.scalar(select(func.count()).select_from(Employee)) == 1
    org_id = db.scalar(select(Employee.telegram_id))
    assert org_id == 4242
    from app.models import Organization

    assert db.scalar(select(Organization.notion_database_id)) == NOTION_DATABASE_ID
    again = choose_sales(db, 4242, "new_sales")
    assert "Вторую запись" in again.text
    assert db.scalar(select(func.count()).select_from(Employee)) == 1
