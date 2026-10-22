"""Postgres fixtures. TELEGRAM_BOT_TOKEN is cleared so tests stay on the test adapter."""

import os
import subprocess
import sys

os.environ.pop("TELEGRAM_BOT_TOKEN", None)
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("NOTION_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("CORPORATE_CHAT_ID", None)
os.environ["APP_ENV"] = "local"
os.environ["LLM_PROVIDER"] = "test"
os.environ["JWT_SECRET"] = "test-only-secret"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = ""
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = ""
os.environ["DATABASE_URL"] = "postgresql+psycopg://hr:hr@127.0.0.1:5432/hr_mvp_test"

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Organization, utcnow
from app.services.org import PAYMENT_FIXED_AMOUNT, PAYMENT_METHOD, PAYMENT_PHONE

get_settings.cache_clear()

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_database() -> None:
    conn = psycopg.connect("postgresql://hr:hr@127.0.0.1:5432/hr", autocommit=True)
    exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = 'hr_mvp_test'").fetchone()
    if not exists:
        conn.execute("CREATE DATABASE hr_mvp_test")
    conn.close()


@pytest.fixture(scope="session")
def engine():
    _ensure_database()
    env = os.environ.copy()
    env["DATABASE_URL"] = os.environ["DATABASE_URL"]
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env)
    sql_engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    yield sql_engine
    sql_engine.dispose()


@pytest.fixture
def db(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    session = factory()
    session.execute(
        text(
            """
            DO $$ DECLARE r RECORD;
            BEGIN
              FOR r IN (
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public' AND tablename <> 'alembic_version'
              ) LOOP
                EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
              END LOOP;
            END $$;
            """
        )
    )
    session.add(
        Organization(
            name="Тестовая",
            timezone="Asia/Almaty",
            greeting_lead_days=7,
            greeting_hour=9,
            llm_model_name="test",
            llm_provider="test",
            currency="KZT",
            payment_method=PAYMENT_METHOD,
            payment_phone=PAYMENT_PHONE,
            payment_fixed_amount=PAYMENT_FIXED_AMOUNT,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    session.commit()
    yield session
    session.close()
