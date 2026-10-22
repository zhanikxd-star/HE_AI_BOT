"""Notion page create. Tests and a missing key never call the network."""

from __future__ import annotations

NOTION_FIELDS = (
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
)


def notion_fields(source: dict) -> dict:
    """Keep only the onboarding fields. Extra HR data is dropped."""
    return {key: source.get(key) for key in NOTION_FIELDS}


def live_create_page(api_key: str, database_id: str, fields: dict) -> None:
    """Send one page. Callers must not use this without a key and a database id."""
    import httpx

    payload = notion_fields(fields)
    properties = {
        "ФИО": {"title": [{"text": {"content": str(payload.get("full_name") or "")}}]},
        "Имя": _rich(payload.get("preferred_name")),
        "Телефон": {"phone_number": payload.get("phone") or None},
        "Дата рождения": _date(payload.get("birth_date")),
        "Должность": _rich(payload.get("position")),
        "Дата выхода": _date(payload.get("hired_at")),
        "Город": _rich(payload.get("city")),
        "Telegram ID": _rich(payload.get("telegram_id")),
        "Telegram username": _rich(payload.get("telegram_username")),
        "Заполнено": _date(payload.get("completed_at")),
    }
    response = httpx.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        json={"parent": {"database_id": database_id}, "properties": properties},
        timeout=30,
    )
    response.raise_for_status()


def _rich(value: object) -> dict:
    return {"rich_text": [{"text": {"content": "" if value is None else str(value)}}]}


def _date(value: object) -> dict:
    if not value:
        return {"date": None}
    return {"date": {"start": str(value)[:10]}}
