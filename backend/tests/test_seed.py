from decimal import Decimal

from sqlalchemy import select

from app.models import Organization
from app.services.org import (
    BOT_USERNAME,
    COMPANY_NAME,
    COMPANY_TIMEZONE,
    CORPORATE_CHAT_ID,
    CORPORATE_CHAT_TITLE,
    CORPORATE_CHAT_TYPE,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    PAYMENT_FIXED_AMOUNT,
    PAYMENT_METHOD,
    NOTION_DATABASE_ID,
    NOTION_DATABASE_TITLE,
    NOTION_DATABASE_TYPE,
    PAYMENT_PHONE,
    SUPER_ADMIN_TELEGRAM_USERNAME,
    apply_corporate_chat_from_env,
    ensure_organization,
    payment_details_text,
)


def test_fresh_org_seed_uses_company_defaults(db):
    current = db.scalar(select(Organization))
    db.delete(current)
    db.commit()
    seeded = ensure_organization(db)
    assert seeded.name == COMPANY_NAME
    assert seeded.timezone == COMPANY_TIMEZONE
    assert seeded.corporate_chat_id == CORPORATE_CHAT_ID
    assert seeded.corporate_chat_title == CORPORATE_CHAT_TITLE
    assert seeded.corporate_chat_type == CORPORATE_CHAT_TYPE
    assert seeded.bot_username == BOT_USERNAME
    assert seeded.super_admin_telegram_username == SUPER_ADMIN_TELEGRAM_USERNAME
    assert seeded.llm_provider == DEFAULT_LLM_PROVIDER
    assert seeded.llm_model_name == DEFAULT_LLM_MODEL
    assert seeded.payment_method == PAYMENT_METHOD
    assert seeded.payment_phone == PAYMENT_PHONE
    assert Decimal(seeded.payment_fixed_amount) == PAYMENT_FIXED_AMOUNT
    assert seeded.currency == "KZT"
    assert seeded.notion_database_id == NOTION_DATABASE_ID
    assert seeded.notion_database_title == NOTION_DATABASE_TITLE
    assert seeded.notion_database_type == NOTION_DATABASE_TYPE
    assert list(seeded.onboarding_files or []) == []
    assert payment_details_text(seeded.payment_phone) == f"Kaspi, перевод по номеру телефона {PAYMENT_PHONE}"
    assert "получател" not in payment_details_text(seeded.payment_phone).lower()
    kept = apply_corporate_chat_from_env(db, None)
    assert kept.corporate_chat_id == CORPORATE_CHAT_ID
    assert apply_corporate_chat_from_env(db, "").corporate_chat_id == CORPORATE_CHAT_ID
