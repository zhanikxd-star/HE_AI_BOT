import json
from datetime import date
from decimal import Decimal

from app.adapters.telegram import FakeTelegramSender
from app.services.org import PAYMENT_FIXED_AMOUNT, PAYMENT_PHONE, payment_details_text
from app.services.collections import (
    create_collection,
    declare_payment,
    dispatch_invites,
    hr_view,
    open_collection,
    peer_view,
    respond,
)
from app.services.employees import EmployeeInput, create_employee


def _employee(db, name, preferred, telegram_id, **kwargs):
    return create_employee(
        db,
        EmployeeInput(
            full_name=name,
            preferred_name=preferred,
            birth_date=kwargs.pop("birth_date", date(1991, 1, 2)),
            telegram_id=telegram_id,
            **kwargs,
        ),
        None,
    )


def test_collection_excludes_birthday_person_and_hides_opt_outs(db):
    sender = FakeTelegramSender()
    birthday = _employee(db, "Аружан Сериккызы", "Аружан", 101, birth_date=date(1995, 5, 5))
    payer = _employee(db, "Данияр Алиев", "Данияр", 102)
    decliner = _employee(db, "Меруерт Нурова", "Меруерт", 103)
    watcher = _employee(db, "Ерлан Садов", "Ерлан", 104)
    _employee(db, "Отказ от программы", "Сания", 105, participate_in_collections=False)
    collection = create_collection(
        db,
        employee_id=birthday.id,
        title="Сбор на подарок",
        description="Добровольный",
        deadline=date(2026, 11, 1),
        scope={"all": True},
        actor_id=None,
    )
    open_collection(db, collection.id, sender, None)
    dispatch_invites(db, collection.id, sender)
    chat_ids = [call["chat_id"] for call in sender.calls]
    assert 101 not in chat_ids
    assert 105 not in chat_ids
    assert sorted(chat_ids) == [102, 103, 104]
    invite = sender.calls[0]["text"]
    assert PAYMENT_PHONE in invite
    assert "5000" in invite
    assert "Ориентир" not in invite
    assert collection.payment_details == payment_details_text(PAYMENT_PHONE)
    assert collection.fixed_amount == PAYMENT_FIXED_AMOUNT
    respond(db, collection.id, payer.id, "accept")
    declare_payment(db, collection.id, payer.id, Decimal("1000"))
    respond(db, collection.id, decliner.id, "decline")
    watcher_view = peer_view(db, collection.id, watcher.id)
    hidden = json.dumps(watcher_view, ensure_ascii=False)
    assert "declined" not in hidden
    assert "Меруерт" not in hidden
    assert "1000" not in hidden
    assert PAYMENT_PHONE in watcher_view["payment_details"]
    assert watcher_view["asked_amount"].startswith("5000")
    visible = hr_view(db, collection.id)
    assert any(row["status"] == "declined" and row["preferred_name"] == "Меруерт" for row in visible["participants"])
    assert any(row["amount"] == "5000.00" for row in visible["participants"])
    assert all(row["employee_id"] != str(birthday.id) for row in visible["participants"])
