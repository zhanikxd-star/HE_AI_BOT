from datetime import datetime, timedelta, timezone

from app.adapters.telegram import FakeTelegramSender
from app.ports import PermanentDeliveryError, SendResult
from app.services.announcements import create_announcement, dispatch_announcement, schedule_announcement, set_rsvp, stats
from app.services.employees import EmployeeInput, create_employee
from app.services.org import create_department


class SelectiveSender:
    def __init__(self):
        self.calls = []

    def send_message(self, chat_id, text, **kwargs):
        self.calls.append(chat_id)
        if chat_id == 303:
            raise PermanentDeliveryError("blocked")
        return SendResult(ok=True, message_id=len(self.calls), provider="telegram")


def test_segment_delivery_and_rsvp(db):
    sales = create_department(db, "Продажи", None)
    other = create_department(db, "Разработка", None)
    reachable = create_employee(
        db,
        EmployeeInput(full_name="Айгуль Ахметова", preferred_name="Айгуль", birth_date=__import__("datetime").date(1990, 2, 2), department_id=sales.id, telegram_id=301),
        None,
    )
    create_employee(
        db,
        EmployeeInput(full_name="Ерлан Беков", preferred_name="Ерлан", birth_date=__import__("datetime").date(1990, 3, 3), department_id=sales.id, bot_status="not_started"),
        None,
    )
    create_employee(
        db,
        EmployeeInput(full_name="Дария Ким", preferred_name="Дария", birth_date=__import__("datetime").date(1990, 4, 4), department_id=sales.id, telegram_id=302, bot_status="blocked"),
        None,
    )
    extra = create_employee(
        db,
        EmployeeInput(full_name="Марат Омаров", preferred_name="Марат", birth_date=__import__("datetime").date(1990, 6, 6), department_id=other.id, telegram_id=304),
        None,
    )
    fresh_block = create_employee(
        db,
        EmployeeInput(full_name="Нурали Ермек", preferred_name="Нурали", birth_date=__import__("datetime").date(1990, 7, 7), department_id=sales.id, telegram_id=303),
        None,
    )
    sender = SelectiveSender()
    announcement = create_announcement(
        db,
        title="Планёрка",
        body="Завтра в 10:00",
        type="meeting",
        segment={"all": False, "department_ids": [str(sales.id)], "employee_ids": [str(extra.id)]},
        requires_rsvp=True,
        image_url=None,
        document_url=None,
        actor_id=None,
    )
    when = datetime.now(timezone.utc) - timedelta(minutes=1)
    schedule_announcement(db, announcement.id, when, None)
    dispatch_announcement(db, announcement.id, sender, now=datetime.now(timezone.utc))
    dispatch_announcement(db, announcement.id, sender, now=datetime.now(timezone.utc))
    payload = stats(db, announcement.id)
    assert payload["delivered"] == 2
    assert payload["not_started"] >= 1
    assert payload["blocked"] >= 1
    assert 303 in sender.calls
    assert len(sender.calls) == 3
    set_rsvp(db, announcement.id, reachable.id, "will_attend")
    set_rsvp(db, announcement.id, extra.id, "cannot_attend")
    payload = stats(db, announcement.id)
    assert payload["will_attend"] == 1
    assert payload["cannot_attend"] == 1
    blocked_row = next(row for row in payload["rows"] if row["employee_id"] == str(fresh_block.id))
    assert blocked_row["delivery_status"] == "blocked"
    assert blocked_row["bot_status"] == "blocked"


def test_not_started_is_not_delivered_with_fake_sender(db):
    sender = FakeTelegramSender()
    person = create_employee(
        db,
        EmployeeInput(full_name="Без бота", preferred_name="Безбота", birth_date=__import__("datetime").date(1988, 1, 1)),
        None,
    )
    announcement = create_announcement(
        db,
        title="Новость",
        body="Текст",
        type="news",
        segment={"all": False, "department_ids": [], "employee_ids": [str(person.id)]},
        requires_rsvp=False,
        image_url=None,
        document_url=None,
        actor_id=None,
    )
    schedule_announcement(db, announcement.id, datetime.now(timezone.utc), None)
    dispatch_announcement(db, announcement.id, sender)
    payload = stats(db, announcement.id)
    assert payload["delivered"] == 0
    assert payload["not_started"] == 1
    assert sender.calls == []
