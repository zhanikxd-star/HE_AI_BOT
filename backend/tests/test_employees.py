from datetime import date

import pytest

from app.domain.rules import (
    duplicate_reasons,
    eligible_collection_participants,
    guard_llm_fields,
    parse_natural_request,
    peer_collection_view,
)
from app.errors import DuplicateEmployeeError, LlmPrivacyError
from app.services.employees import EmployeeInput, create_employee, import_rows


def test_duplicate_reasons_match_name_and_username():
    existing = [
        {
            "id": "1",
            "full_name": "Аружан Сериккызы",
            "birth_date": date(1995, 5, 5),
            "telegram_id": None,
            "telegram_username": "Aru",
            "source": "database",
        }
    ]
    matches = duplicate_reasons(
        {"full_name": "  аружан   сериккызы ", "birth_date": date(1995, 5, 5), "telegram_id": None, "telegram_username": None},
        existing,
    )
    assert matches[0]["reasons"] == ["name_birth_date"]
    username = duplicate_reasons(
        {"full_name": "Другой", "birth_date": date(1990, 1, 1), "telegram_id": None, "telegram_username": "@ARU"},
        existing,
    )
    assert username[0]["reasons"] == ["telegram_username"]


def test_birthday_person_is_excluded_even_if_listed():
    people = [
        {"id": "b", "status": "active", "department_id": "d", "participate_in_collections": True},
        {"id": "a", "status": "active", "department_id": "d", "participate_in_collections": True},
    ]
    selected = eligible_collection_participants(people, "b", {"all": False, "department_ids": [], "employee_ids": ["b", "a"]})
    assert [row["id"] for row in selected] == ["a"]


def test_peer_view_hides_other_people():
    view = peer_collection_view(
        {"id": "c", "title": "Сбор", "description": "", "deadline": None, "currency": "KZT", "contribution_mode": "fixed", "fixed_amount": "5000.00", "payment_details": "Kaspi, перевод по номеру телефона +77029994897", "status": "open"},
        {"status": "invited", "amount": None},
    )
    assert "participants" not in view
    assert view["payment_details"]
    assert view["asked_amount"] == "5000.00"
    assert view["own_amount"] is None
    assert "declined" not in str(view)


def test_llm_guard_rejects_telegram_id():
    with pytest.raises(LlmPrivacyError):
        guard_llm_fields("greeting", {"preferred_name": "Аружан", "telegram_id": 1})


def test_natural_request_finds_name_and_amount():
    parsed = parse_natural_request(
        "Поздравь завтра Аружан с днём рождения и подготовь сбор на подарок на 25 000 тенге",
        ["Данияр", "Аружан"],
    )
    assert parsed["intent"]["employee_preferred_name"] == "Аружан"
    assert parsed["intent"]["amount"] == 25000
    assert "greeting" in parsed["intent"]["actions"]
    assert "collection" in parsed["intent"]["actions"]


def test_import_skips_duplicate_and_keeps_new_row(db):
    create_employee(
        db,
        EmployeeInput(full_name="Аружан Сериккызы", preferred_name="Аружан", birth_date=date(1995, 5, 5)),
        None,
    )
    report = import_rows(
        db,
        [
            {"full_name": "Аружан Сериккызы", "preferred_name": "Аружан", "birth_date": "1995-05-05", "department": "Продажи"},
            {"full_name": "Данияр Алиев", "preferred_name": "Данияр", "birth_date": "1992-03-03", "department": "Продажи"},
        ],
        None,
    )
    assert report["created"] == 1
    assert len(report["duplicates"]) == 1
    with pytest.raises(DuplicateEmployeeError):
        create_employee(
            db,
            EmployeeInput(full_name="Данияр Алиев", preferred_name="Данияр", birth_date=date(1992, 3, 3)),
            None,
        )
