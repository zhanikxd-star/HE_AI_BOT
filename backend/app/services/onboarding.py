"""Sales onboarding. The employee row is always local. Notion runs only with a key and a database id."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.notion import live_create_page, notion_fields
from app.config import get_settings
from app.errors import DomainError, DuplicateEmployeeError
from app.models import Employee, OnboardingApplication, utcnow
from app.services.audit import write_audit
from app.services.employees import EmployeeInput, create_employee, ensure_department, find_by_telegram
from app.services.org import SALES_DEPARTMENT, get_org

logger = logging.getLogger(__name__)

STEPS = ("full_name", "preferred_name", "phone", "birth_date", "position", "hired_at", "city", "consent")
PROMPTS = {
    "full_name": "Напиши ФИО полностью.",
    "preferred_name": "Как к тебе обращаться?",
    "phone": "Напиши номер телефона.",
    "birth_date": "Дата рождения в формате ДД.ММ.ГГГГ.",
    "position": "Какая должность?",
    "hired_at": "Дата выхода в формате ДД.ММ.ГГГГ.",
    "city": "В каком ты городе?",
    "consent": "Можно поздравлять тебя в корпоративном чате? Пока не выберешь, согласие не включается.",
}
TRAINING_EMPTY = "Материалы обучения ещё не загружены."


@dataclass
class Reply:
    text: str
    choice: bool = False
    consent: bool = False
    menu: bool = False
    documents: list[dict] = field(default_factory=list)


def greet(session: Session, telegram_id: int) -> Reply:
    employee = find_by_telegram(session, telegram_id)
    if employee is not None:
        return Reply(f"{employee.preferred_name}, ты уже в команде.", menu=True)
    return Reply("Привет. Я HR-бот Impact Admissions. Выбери, что тебе подходит.", choice=True)


def choose_existing(session: Session, telegram_id: int) -> Reply:
    employee = find_by_telegram(session, telegram_id)
    if employee is not None:
        return Reply(f"{employee.preferred_name}, ты уже в команде. Анкету заново не заполняем.", menu=True)
    draft = _draft(session, telegram_id, None)
    if draft is not None and draft.status == "in_progress":
        draft.status = "cancelled"
        draft.updated_at = utcnow()
        session.commit()
    return Reply("Тогда открой персональную ссылку от HR. Анкету отдела продаж и Notion в этом случае не заполняем.")


def choose_sales(session: Session, telegram_id: int, username: str | None) -> Reply:
    employee = find_by_telegram(session, telegram_id)
    if employee is not None:
        return Reply(f"{employee.preferred_name}, ты уже в команде. Вторую запись не создаю.", menu=True)
    draft = _open_draft(session, telegram_id, username)
    if draft.status == "completed" and draft.employee_id:
        return Reply("Анкета уже сохранена. Вторую запись не создаю.", menu=True)
    return Reply(PROMPTS[draft.step], consent=draft.step == "consent")


def answer(session: Session, telegram_id: int, username: str | None, text: str) -> Reply:
    draft = _open_draft(session, telegram_id, username)
    if draft.status == "completed":
        return Reply("Анкета уже сохранена. Вторую запись не создаю.", menu=True)
    if draft.step == "consent":
        return Reply(PROMPTS["consent"], consent=True)
    value = _parse(draft.step, text)
    answers = dict(draft.answers or {})
    answers[draft.step] = value
    draft.answers = answers
    draft.step = STEPS[STEPS.index(draft.step) + 1]
    draft.updated_at = utcnow()
    session.commit()
    if draft.step == "consent":
        return Reply(PROMPTS["consent"], consent=True)
    return Reply(PROMPTS[draft.step])


def set_consent(session: Session, telegram_id: int, username: str | None, consent: bool) -> Reply:
    draft = _open_draft(session, telegram_id, username)
    if draft.status == "completed" and draft.employee_id:
        return Reply("Анкета уже сохранена. Вторую запись не создаю.", menu=True)
    answers = dict(draft.answers or {})
    answers["consent"] = bool(consent)
    draft.answers = answers
    draft.step = "consent"
    return _finish(session, draft, username)


def _finish(session: Session, draft: OnboardingApplication, username: str | None) -> Reply:
    if find_by_telegram(session, draft.telegram_id) is not None:
        return Reply("Ты уже в команде. Вторую запись не создаю.", menu=True)
    answers = dict(draft.answers or {})
    try:
        department = ensure_department(session, SALES_DEPARTMENT)
        employee = create_employee(
            session,
            EmployeeInput(
                full_name=answers["full_name"],
                preferred_name=answers["preferred_name"],
                birth_date=_as_date(answers["birth_date"]),
                department_id=department.id,
                position=answers.get("position") or "",
                phone=answers.get("phone") or "",
                city=answers.get("city") or "",
                telegram_id=draft.telegram_id,
                telegram_username=username or draft.telegram_username,
                hired_at=_as_date(answers["hired_at"]),
                public_greeting_consent=bool(answers.get("consent", False)),
                status="active",
            ),
            None,
        )
    except DuplicateEmployeeError:
        draft.notion_status = "skipped"
        draft.notion_error = "duplicate_employee"
        draft.updated_at = utcnow()
        session.commit()
        return Reply("Такой сотрудник уже есть. Вторую запись не создаю. Открой персональную ссылку от HR.")
    completed = utcnow()
    draft.employee_id = employee.id
    draft.status = "completed"
    draft.completed_at = completed
    draft.updated_at = completed
    _sync_notion(session, draft, employee, completed)
    write_audit(session, None, "onboarding.complete", "employee", employee.id, {"notion_status": draft.notion_status})
    session.commit()
    org = get_org(session)
    documents = [item for item in (org.onboarding_files or []) if isinstance(item, dict) and item.get("url")]
    training = TRAINING_EMPTY if not documents else "Материалы обучения отправлены."
    return Reply(f"{employee.preferred_name}, анкета сохранена. Ты в отделе продаж. {training}", menu=True, documents=documents)


def _sync_notion(session: Session, draft: OnboardingApplication, employee: Employee, completed: datetime) -> None:
    settings = get_settings()
    org = get_org(session)
    record = notion_fields(
        {
            "full_name": employee.full_name,
            "preferred_name": employee.preferred_name,
            "phone": employee.phone,
            "birth_date": employee.birth_date.isoformat(),
            "position": employee.position,
            "hired_at": employee.hired_at.isoformat() if employee.hired_at else None,
            "city": employee.city,
            "telegram_id": employee.telegram_id,
            "telegram_username": employee.telegram_username,
            "completed_at": completed.isoformat(),
            "public_greeting_consent": employee.public_greeting_consent,
            "invite_token": employee.invite_token,
        }
    )
    api_key = settings.notion_api_key
    database_id = org.notion_database_id
    if not api_key or not database_id:
        reason = "missing_key" if not api_key else "missing_database_id"
        draft.notion_status = "skipped"
        draft.notion_error = reason
        logger.error(
            "notion skipped",
            extra={"event": "notion_skipped", "entity_type": "onboarding", "entity_id": str(draft.id)},
        )
        return
    try:
        live_create_page(api_key, database_id, record)
    except Exception:
        logger.exception(
            "notion request failed",
            extra={"event": "notion_failed", "entity_type": "onboarding", "entity_id": str(draft.id)},
        )
        draft.notion_status = "failed"
        draft.notion_error = "notion_request_failed"
        return
    draft.notion_status = "synced"
    draft.notion_error = None


def _open_draft(session: Session, telegram_id: int, username: str | None) -> OnboardingApplication:
    draft = _draft(session, telegram_id, username)
    if draft is None:
        draft = OnboardingApplication(
            telegram_id=telegram_id,
            telegram_username=username,
            status="in_progress",
            step="full_name",
            answers={},
            notion_status="pending",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(draft)
    elif draft.status != "in_progress":
        if draft.status == "completed" and draft.employee_id:
            return draft
        draft.status = "in_progress"
        draft.step = "full_name"
        draft.answers = {}
        draft.employee_id = None
        draft.notion_status = "pending"
        draft.notion_error = None
    if username:
        draft.telegram_username = username.lstrip("@")
    draft.updated_at = utcnow()
    session.commit()
    return draft


def _draft(session: Session, telegram_id: int, username: str | None) -> OnboardingApplication | None:
    return session.scalar(select(OnboardingApplication).where(OnboardingApplication.telegram_id == telegram_id))


def active_application(session: Session, telegram_id: int) -> OnboardingApplication | None:
    return session.scalar(
        select(OnboardingApplication).where(
            OnboardingApplication.telegram_id == telegram_id,
            OnboardingApplication.status == "in_progress",
        )
    )


def _parse(step: str, text: str) -> str:
    clean = " ".join((text or "").split())
    if not clean:
        raise DomainError("Пустой ответ")
    if step in {"birth_date", "hired_at"}:
        return _as_date(clean).isoformat()
    if step == "phone":
        digits = "".join(char for char in clean if char.isdigit())
        if len(digits) < 10:
            raise DomainError("Нужен номер телефона")
        return clean
    return clean


def _as_date(value: str):
    raw = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise DomainError("Дата в формате ДД.ММ.ГГГГ")


def employee_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(Employee)) or 0)
