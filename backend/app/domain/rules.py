"""Identity, calendar, delivery, collection privacy, and LLM field guard."""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.errors import LlmPrivacyError

FORBIDDEN_LLM_KEYS = frozenset(
    {
        "telegram_id",
        "telegram_username",
        "telegram_chat_id",
        "full_name",
        "birth_date",
        "birth_year",
        "hired_at",
        "phone",
        "email",
        "invite_token",
        "payment_details",
        "amount",
        "contribution",
        "password",
        "password_hash",
    }
)

ALLOWED_LLM_FIELDS: dict[str, frozenset[str]] = {
    "greeting": frozenset({"preferred_name", "position", "department", "style", "variant"}),
    "announcement": frozenset({"title", "announcement_type", "style", "audience_label", "current_text"}),
    "collection": frozenset({"preferred_name", "budget_amount", "currency", "deadline"}),
    "gift_ideas": frozenset({"preferred_name", "budget_amount", "currency"}),
    "nl_command": frozenset({"instruction", "candidate_names"}),
}

DELIVERED_STATUS = "sent"
TERMINAL_GREETING = frozenset(
    {"sent", "simulated", "sending", "cancelled", "skipped_no_consent", "failed"}
)
NO_RESEND = frozenset({"sent", "simulated", "sending", "cancelled", "skipped_no_consent"})


def normalize_name(value: str) -> str:
    text = value.strip().lower().replace("ё", "е")
    return " ".join(text.split())


def normalize_username(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lstrip("@").lower()
    return text or None


def safe_birthday(birth: date, year: int) -> date:
    try:
        return date(year, birth.month, birth.day)
    except ValueError:
        return date(year, 2, 28)


def occasion_on_or_after(birth: date, today: date) -> date:
    occasion = safe_birthday(birth, today.year)
    if occasion < today:
        return safe_birthday(birth, today.year + 1)
    return occasion


def days_until_birthday(birth: date, today: date) -> int:
    return (occasion_on_or_after(birth, today) - today).days


def org_local_date(now: datetime, timezone_name: str) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo(timezone_name)).date()


def default_greeting_send_at(occasion: date, timezone_name: str, hour: int) -> datetime:
    from datetime import timezone

    local = datetime(occasion.year, occasion.month, occasion.day, hour, 0, tzinfo=ZoneInfo(timezone_name))
    return local.astimezone(timezone.utc)


def duplicate_reasons(
    candidate: dict,
    existing: list[dict],
) -> list[dict]:
    """Return matches against existing identities.

    A row is a duplicate when telegram id matches, telegram username matches,
    or the normalized full name and birth date match.
    """
    name = normalize_name(candidate["full_name"])
    username = normalize_username(candidate.get("telegram_username"))
    telegram_id = candidate.get("telegram_id")
    birth = candidate["birth_date"]
    found: list[dict] = []
    for row in existing:
        reasons: list[str] = []
        if telegram_id is not None and row.get("telegram_id") is not None and int(row["telegram_id"]) == int(telegram_id):
            reasons.append("telegram_id")
        row_username = normalize_username(row.get("telegram_username"))
        if username and row_username and username == row_username:
            reasons.append("telegram_username")
        if normalize_name(row["full_name"]) == name and row["birth_date"] == birth:
            reasons.append("name_birth_date")
        if reasons:
            found.append({"id": row.get("id"), "reasons": reasons, "source": row.get("source", "database")})
    return found


def initial_delivery_status(employee: dict, channel: str) -> str:
    settings = employee.get("notification_settings") or {}
    if channel == "announcements" and not settings.get("announcements", True):
        return "notifications_off"
    if channel == "collections" and not settings.get("collections", True):
        return "notifications_off"
    if employee.get("bot_status") == "blocked":
        return "blocked"
    if employee.get("bot_status") != "active" or not employee.get("telegram_id"):
        return "not_started"
    return "pending"


def is_delivered(status: str) -> bool:
    return status == DELIVERED_STATUS


def in_segment(employee: dict, segment: dict) -> bool:
    if employee.get("status") != "active":
        return False
    if segment.get("all"):
        return True
    department_ids = {str(item) for item in segment.get("department_ids") or []}
    employee_ids = {str(item) for item in segment.get("employee_ids") or []}
    department_id = employee.get("department_id")
    if department_id is not None and str(department_id) in department_ids:
        return True
    return str(employee["id"]) in employee_ids


def eligible_collection_participants(employees: list[dict], birthday_employee_id: str, scope: dict) -> list[dict]:
    selected: list[dict] = []
    birthday = str(birthday_employee_id)
    for employee in employees:
        if str(employee["id"]) == birthday:
            continue
        if employee.get("status") != "active":
            continue
        if not employee.get("participate_in_collections", True):
            continue
        if in_segment(employee, scope):
            selected.append(employee)
    return selected


def peer_collection_view(collection: dict, participant: dict) -> dict:
    """What one invited employee may see. No peer opt-outs and no peer amounts."""
    own_status = participant["status"]
    show_details = own_status in {"accepted", "payment_declared", "confirmed"}
    return {
        "id": collection["id"],
        "title": collection["title"],
        "description": collection.get("description") or "",
        "deadline": collection.get("deadline"),
        "currency": collection.get("currency"),
        "contribution_mode": collection.get("contribution_mode"),
        "asked_amount": collection.get("fixed_amount") if collection.get("contribution_mode") == "fixed" else None,
        "own_status": own_status,
        "own_amount": participant.get("amount") if show_details else None,
        "payment_details": collection.get("payment_details") or None,
        "collection_status": collection.get("status"),
    }


def hr_collection_view(collection: dict, participants: list[dict]) -> dict:
    confirmed = [row for row in participants if row["status"] == "confirmed"]
    declared = [row for row in participants if row["status"] == "payment_declared"]
    return {
        **collection,
        "participants": participants,
        "confirmed_sum": _sum_amounts(confirmed),
        "declared_unconfirmed_sum": _sum_amounts(declared),
        "delivered_count": sum(1 for row in participants if is_delivered(row["delivery_status"])),
        "not_delivered_count": sum(1 for row in participants if not is_delivered(row["delivery_status"])),
    }


def _sum_amounts(rows: list[dict]) -> str:
    total = 0
    for row in rows:
        if row.get("amount") is not None:
            total += int(round(float(row["amount"]) * 100))
    return f"{total / 100:.2f}"


def guard_llm_fields(task: str, fields: dict) -> dict:
    allowed = ALLOWED_LLM_FIELDS.get(task)
    if allowed is None:
        raise LlmPrivacyError(task)
    clean: dict = {}
    for key, value in fields.items():
        if key in FORBIDDEN_LLM_KEYS or key not in allowed:
            raise LlmPrivacyError(key)
        if isinstance(value, dict):
            raise LlmPrivacyError(key)
        clean[key] = value
    return clean


def parse_natural_request(instruction: str, candidate_names: list[str]) -> dict:
    """Deterministic reading of an HR instruction. Used by the test adapter."""
    lowered = instruction.lower()
    amount = None
    amount_match = re.search(r"(\d[\d \u00a0]{0,14})\s*(тенге|kzt|₸)", instruction, flags=re.IGNORECASE)
    if amount_match:
        amount = int(re.sub(r"[ \u00a0]", "", amount_match.group(1)))
    when = None
    if "завтра" in lowered:
        when = "tomorrow"
    elif "сегодня" in lowered:
        when = "today"
    matched = None
    for name in sorted(candidate_names, key=len, reverse=True):
        if name and name.lower() in lowered:
            matched = name
            break
    actions: list[str] = []
    if "поздрав" in lowered:
        actions.append("greeting")
    if "сбор" in lowered or "подар" in lowered:
        actions.append("collection")
    greeting_text = None
    if matched and "greeting" in actions:
        greeting_text = f"{matched}, с днём рождения! Команда поздравляет тебя и желает тёплого дня."
    collection = None
    if "collection" in actions:
        collection = {
            "title": f"Сбор на подарок — {matched}" if matched else "Сбор на подарок",
            "description": "Участие добровольное. Отказ не нужно объяснять.",
            "contribution_mode": "fixed",
        }
    return {
        "intent": {
            "actions": actions,
            "employee_preferred_name": matched,
            "when": when,
            "amount": amount,
            "currency": "KZT" if amount is not None else None,
        },
        "greeting_text": greeting_text,
        "collection": collection,
    }


def announcement_stats(rows: list[dict]) -> dict:
    def count(status: str) -> int:
        return sum(1 for row in rows if row["delivery_status"] == status)

    return {
        "recipients": len(rows),
        "delivered": count("sent"),
        "simulated": count("simulated"),
        "pending": count("pending") + count("sending"),
        "not_started": count("not_started"),
        "blocked": count("blocked"),
        "notifications_off": count("notifications_off"),
        "failed": count("failed"),
        "will_attend": sum(1 for row in rows if row.get("rsvp_status") == "will_attend"),
        "cannot_attend": sum(1 for row in rows if row.get("rsvp_status") == "cannot_attend"),
    }
