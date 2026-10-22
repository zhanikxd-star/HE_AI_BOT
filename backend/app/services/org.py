"""Organization settings, departments, and local-only admin bootstrap."""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import DomainError, NotFoundError
from app.models import Department, Organization, User, utcnow
from app.security import hash_password
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

COMPANY_NAME = "Impact Admissions"
COMPANY_TIMEZONE = "Asia/Almaty"
BOT_USERNAME = "magripaharip_bot"
SUPER_ADMIN_TELEGRAM_USERNAME = "Kapanov_30"
CORPORATE_CHAT_ID = -1002615527142
CORPORATE_CHAT_TITLE = "Контент impact"
CORPORATE_CHAT_TYPE = "supergroup"
DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
PAYMENT_METHOD = "kaspi_phone"
PAYMENT_PHONE = "+77029994897"
PAYMENT_FIXED_AMOUNT = Decimal("5000.00")
NOTION_DATABASE_ID = "40159421a41f80c1bfd5ce5b06de3213"
NOTION_DATABASE_TITLE = "Document Hub"
NOTION_DATABASE_TYPE = "database"
SALES_DEPARTMENT = "Отдел продаж"


def payment_details_text(phone: str) -> str:
    """Kaspi transfer by phone. The recipient display name is unknown and is not invented."""
    return f"Kaspi, перевод по номеру телефона {phone.strip()}"


def _training_files(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        raise DomainError("Список файлов обучения должен быть массивом")
    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DomainError("Файл обучения: название и ссылка")
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not name or not url:
            raise DomainError("У файла обучения нужны название и ссылка")
        cleaned.append({"name": name, "url": url})
    return cleaned


def normalize_public_username(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lstrip("@")
    return text or None


def apply_corporate_chat_from_env(session: Session, raw: str | None) -> Organization:
    """Apply CORPORATE_CHAT_ID when it is set. An empty value does not erase the seeded id."""
    org = ensure_organization(session)
    if raw is None or str(raw).strip() == "":
        return org
    org.corporate_chat_id = int(str(raw).strip())
    org.updated_at = utcnow()
    session.commit()
    return org


def get_org(session: Session) -> Organization:
    org = session.scalar(select(Organization).limit(1))
    if org is None:
        raise DomainError("Организация не настроена")
    return org


def ensure_organization(session: Session) -> Organization:
    org = session.scalar(select(Organization).limit(1))
    if org is not None:
        return org
    org = Organization(
        name=COMPANY_NAME,
        timezone=COMPANY_TIMEZONE,
        corporate_chat_id=CORPORATE_CHAT_ID,
        corporate_chat_title=CORPORATE_CHAT_TITLE,
        corporate_chat_type=CORPORATE_CHAT_TYPE,
        greeting_lead_days=7,
        greeting_hour=9,
        llm_model_name=DEFAULT_LLM_MODEL,
        llm_provider=DEFAULT_LLM_PROVIDER,
        currency="KZT",
        payment_method=PAYMENT_METHOD,
        payment_phone=PAYMENT_PHONE,
        payment_fixed_amount=PAYMENT_FIXED_AMOUNT,
        notion_database_id=NOTION_DATABASE_ID,
        notion_database_title=NOTION_DATABASE_TITLE,
        notion_database_type=NOTION_DATABASE_TYPE,
        onboarding_files=[],
        bot_username=BOT_USERNAME,
        super_admin_telegram_username=SUPER_ADMIN_TELEGRAM_USERNAME,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(org)
    session.commit()
    return org


def update_organization(session: Session, actor_id: UUID, changes: dict) -> Organization:
    org = get_org(session)
    if "timezone" in changes and changes["timezone"]:
        try:
            ZoneInfo(changes["timezone"])
        except Exception as exc:
            raise DomainError("Неизвестный часовой пояс") from exc
        org.timezone = changes["timezone"]
    if "name" in changes and changes["name"]:
        org.name = str(changes["name"]).strip()
    if "corporate_chat_id" in changes:
        value = changes["corporate_chat_id"]
        org.corporate_chat_id = int(value) if value not in (None, "") else None
    if "greeting_lead_days" in changes and changes["greeting_lead_days"] is not None:
        days = int(changes["greeting_lead_days"])
        if days < 1 or days > 30:
            raise DomainError("Срок уведомления HR должен быть от 1 до 30 дней")
        org.greeting_lead_days = days
    if "greeting_hour" in changes and changes["greeting_hour"] is not None:
        hour = int(changes["greeting_hour"])
        if hour < 0 or hour > 23:
            raise DomainError("Час отправки должен быть от 0 до 23")
        org.greeting_hour = hour
    if "llm_model_name" in changes and changes["llm_model_name"]:
        org.llm_model_name = str(changes["llm_model_name"]).strip()
    if "llm_provider" in changes and changes["llm_provider"]:
        provider = str(changes["llm_provider"]).strip()
        if provider not in {"test", "openai"}:
            raise DomainError("Провайдер модели: test или openai")
        org.llm_provider = provider
    if "payment_phone" in changes and changes["payment_phone"] is not None:
        phone = str(changes["payment_phone"]).strip()
        if not phone.startswith("+") or not phone[1:].isdigit():
            raise DomainError("Номер для Kaspi укажите в международном формате")
        org.payment_phone = phone
    if "payment_fixed_amount" in changes and changes["payment_fixed_amount"] is not None:
        amount = Decimal(str(changes["payment_fixed_amount"]))
        if amount <= 0:
            raise DomainError("Фиксированный взнос должен быть больше нуля")
        org.payment_fixed_amount = amount
    if "currency" in changes and changes["currency"]:
        org.currency = str(changes["currency"]).strip().upper()
    if "bot_username" in changes:
        username = normalize_public_username(changes.get("bot_username"))
        org.bot_username = username
    if "super_admin_telegram_username" in changes:
        org.super_admin_telegram_username = normalize_public_username(changes.get("super_admin_telegram_username"))
    if "notion_database_id" in changes:
        raw = changes.get("notion_database_id")
        org.notion_database_id = str(raw).strip() or None if raw is not None else None
    if "onboarding_files" in changes and changes["onboarding_files"] is not None:
        org.onboarding_files = _training_files(changes["onboarding_files"])
    org.updated_at = utcnow()
    write_audit(session, actor_id, "settings.update", "organization", org.id, {"fields": sorted(changes)})
    session.commit()
    return org


def list_departments(session: Session) -> list[Department]:
    return list(session.scalars(select(Department).order_by(Department.name)))


def create_department(session: Session, name: str, actor_id: UUID | None) -> Department:
    clean = " ".join(name.strip().split())
    if not clean:
        raise DomainError("Укажите название подразделения")
    existing = session.scalar(select(Department).where(Department.name == clean))
    if existing:
        raise DomainError("Такое подразделение уже есть")
    department = Department(name=clean, is_active=True)
    session.add(department)
    write_audit(session, actor_id, "department.create", "department", department.id, {"name": clean})
    session.commit()
    return department


def authenticate(session: Session, email: str, password: str) -> User:
    from app.security import verify_password

    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise DomainError("Неверная почта или пароль", "auth")
    return user


def create_admin(session: Session, actor_id: UUID, email: str, password: str, full_name: str, role: str) -> User:
    if role not in {"super_admin", "hr_admin"}:
        raise DomainError("Неизвестная роль")
    if len(password) < 8:
        raise DomainError("Пароль не короче 8 символов")
    normalized = email.strip().lower()
    if session.scalar(select(User).where(User.email == normalized)):
        raise DomainError("Пользователь с такой почтой уже есть")
    user = User(
        email=normalized,
        password_hash=hash_password(password),
        full_name=full_name.strip() or normalized,
        role=role,
        is_active=True,
        created_at=utcnow(),
    )
    session.add(user)
    write_audit(session, actor_id, "admin.create", "user", user.id, {"email": normalized, "role": role})
    session.commit()
    return user


def update_admin(session: Session, actor_id: UUID, user_id: UUID, *, role: str | None, is_active: bool | None) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    if role is not None:
        if role not in {"super_admin", "hr_admin"}:
            raise DomainError("Неизвестная роль")
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if user.role != "super_admin" or not user.is_active:
        admins = session.scalar(
            select(func.count()).select_from(User).where(User.role == "super_admin", User.is_active.is_(True), User.id != user.id)
        )
        if not admins and (user.role != "super_admin" or not user.is_active):
            raise DomainError("Нельзя отключить последнего суперадмина")
    write_audit(session, actor_id, "admin.update", "user", user.id, {"role": user.role, "is_active": user.is_active})
    session.commit()
    return user


def list_admins(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.created_at)))


def bootstrap_local_admin(session: Session, settings: Settings) -> User | None:
    """Create the first super admin only for APP_ENV=local. Never used as a production backdoor."""
    ensure_organization(session)
    if settings.app_env != "local":
        return None
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return None
    existing = session.scalar(select(func.count()).select_from(User))
    if existing:
        return None
    user = User(
        email=settings.bootstrap_admin_email.strip().lower(),
        password_hash=hash_password(settings.bootstrap_admin_password),
        full_name="Локальный администратор",
        role="super_admin",
        is_active=True,
        telegram_username=normalize_public_username(settings.super_admin_telegram_username) or SUPER_ADMIN_TELEGRAM_USERNAME,
        created_at=utcnow(),
    )
    session.add(user)
    session.flush()
    write_audit(
        session,
        None,
        "admin.bootstrap_local",
        "user",
        user.id,
        {"email": user.email, "local_only": True},
    )
    session.commit()
    logger.warning("LOCAL ONLY bootstrap super admin created", extra={"event": "bootstrap_admin"})
    return user
