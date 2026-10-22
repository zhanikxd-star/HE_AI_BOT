"""HTTP API for HR admins. Employees use the bot, not these routes."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.llm import build_llm, llm_runtime_mode
from app.api.deps import get_db, get_sender, require
from app.api.schemas import (
    AdminIn,
    AdminPatch,
    AiDraftIn,
    AnnouncementIn,
    AnnouncementPatch,
    CollectionIn,
    CollectionPatch,
    ConfirmIn,
    DepartmentIn,
    EmployeeIn,
    EmployeePatch,
    GreetingApproveIn,
    LoginIn,
    ScheduleIn,
    SettingsPatch,
)
from app.api.serialize import department_map, employee_json, iso, money
from app.config import get_settings
from app.models import AuditLog, Employee, User
from app.security import create_access_token
from app.services import ai as ai_service
from app.services import announcements as announcement_service
from app.services import collections as collection_service
from app.services import dashboard as dashboard_service
from app.services import employees as employee_service
from app.services import greetings as greeting_service
from app.services import org as org_service
from app.services.employees import EmployeeInput
from app.services.org import payment_details_text
from app.services.scheduler import run_due

router = APIRouter(prefix="/api")
HR = require("super_admin", "hr_admin")
SUPER = require("super_admin")


@router.get("/health")
def health(session: Session = Depends(get_db)):
    settings = get_settings()
    org = org_service.ensure_organization(session)
    provider = org.llm_provider or settings.llm_provider
    return {
        "status": "ok",
        "telegram": "live" if settings.telegram_bot_token else "test",
        "llm": llm_runtime_mode(provider, settings.openai_api_key),
        "env": settings.app_env,
    }


@router.post("/auth/login")
def login(body: LoginIn, session: Session = Depends(get_db)):
    user = org_service.authenticate(session, body.email, body.password)
    settings = get_settings()
    return {
        "access_token": create_access_token(user.id, user.role, settings),
        "token_type": "bearer",
        "role": user.role,
        "full_name": user.full_name,
        "email": user.email,
    }


@router.get("/auth/me")
def me(user: User = Depends(HR)):
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role}


@router.get("/dashboard")
def dashboard(session: Session = Depends(get_db), _: User = Depends(HR)):
    return dashboard_service.dashboard(session)


@router.get("/calendar")
def calendar(year: int, month: int, session: Session = Depends(get_db), _: User = Depends(HR)):
    return dashboard_service.month_calendar(session, year, month)


@router.get("/departments")
def departments(session: Session = Depends(get_db), _: User = Depends(HR)):
    return [{"id": str(item.id), "name": item.name, "is_active": item.is_active} for item in org_service.list_departments(session)]


@router.post("/departments")
def create_department(body: DepartmentIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    item = org_service.create_department(session, body.name, user.id)
    return {"id": str(item.id), "name": item.name, "is_active": item.is_active}


@router.get("/employees")
def employees(
    q: str | None = None,
    status: str | None = None,
    department_id: str | None = None,
    bot_status: str | None = None,
    session: Session = Depends(get_db),
    _: User = Depends(HR),
):
    from uuid import UUID

    dep = UUID(department_id) if department_id else None
    names = department_map(session)
    rows = employee_service.list_employees(session, query=q, status=status, department_id=dep, bot_status=bot_status)
    return [employee_json(row, names) for row in rows]


@router.post("/employees")
def create_employee(body: EmployeeIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    employee = employee_service.create_employee(session, _input(body), user.id)
    return employee_json(employee, department_map(session))


@router.get("/employees/{employee_id}")
def get_employee(employee_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    employee = employee_service.get_employee(session, UUID(employee_id))
    return employee_json(employee, department_map(session))


@router.patch("/employees/{employee_id}")
def patch_employee(employee_id: str, body: EmployeePatch, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    current = employee_service.get_employee(session, UUID(employee_id))
    data = body.model_dump(exclude_unset=True)
    merged = EmployeeInput(
        full_name=data.get("full_name", current.full_name),
        preferred_name=data.get("preferred_name", current.preferred_name),
        birth_date=data.get("birth_date", current.birth_date),
        department_id=data["department_id"] if "department_id" in data else current.department_id,
        position=data.get("position", current.position),
        phone=data.get("phone", current.phone),
        city=data.get("city", current.city),
        telegram_id=data["telegram_id"] if "telegram_id" in data else current.telegram_id,
        telegram_username=data["telegram_username"] if "telegram_username" in data else current.telegram_username,
        hired_at=data["hired_at"] if "hired_at" in data else current.hired_at,
        public_greeting_consent=data.get("public_greeting_consent", current.public_greeting_consent),
        participate_in_collections=data.get("participate_in_collections", current.participate_in_collections),
        notification_settings=data.get("notification_settings", current.notification_settings),
        status=data.get("status", current.status),
    )
    employee = employee_service.update_employee(session, current.id, merged, user.id)
    return employee_json(employee, department_map(session))


@router.post("/employees/{employee_id}/deactivate")
def deactivate(employee_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    employee = employee_service.deactivate_employee(session, UUID(employee_id), user.id)
    return employee_json(employee, department_map(session))


@router.post("/employees/{employee_id}/invite")
def invite(employee_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    employee = employee_service.get_employee(session, UUID(employee_id))
    username = get_settings().telegram_bot_username or org_service.get_org(session).bot_username
    link = f"https://t.me/{username}?start={employee.invite_token}" if username else None
    return {"invite_token": employee.invite_token, "start_payload": employee.invite_token, "link": link}


@router.post("/employees/import")
async def import_employees(file: UploadFile = File(...), session: Session = Depends(get_db), user: User = Depends(HR)):
    content = await file.read()
    name = (file.filename or "").lower()
    rows = employee_service.parse_xlsx(content) if name.endswith(".xlsx") else employee_service.parse_csv(content)
    return employee_service.import_rows(session, rows, user.id)


@router.get("/greetings")
def greetings(status: str | None = None, session: Session = Depends(get_db), _: User = Depends(HR)):
    names = {row.id: row for row in session.scalars(select(Employee))}
    return [_greeting_json(item, names.get(item.employee_id)) for item in greeting_service.list_greetings(session, status)]


@router.post("/greetings/scan")
def scan(session: Session = Depends(get_db), sender=Depends(get_sender), _: User = Depends(HR)):
    return greeting_service.scan_birthdays(session, sender=sender)


@router.post("/greetings/{greeting_id}/approve")
def approve_greeting(greeting_id: str, body: GreetingApproveIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    greeting = greeting_service.approve_greeting(session, UUID(greeting_id), user.id, body.text, body.scheduled_for)
    employee = session.get(Employee, greeting.employee_id)
    return _greeting_json(greeting, employee)


@router.post("/greetings/{greeting_id}/cancel")
def cancel_greeting(greeting_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    greeting = greeting_service.cancel_greeting(session, UUID(greeting_id), user.id)
    employee = session.get(Employee, greeting.employee_id)
    return _greeting_json(greeting, employee)


@router.get("/collections")
def collections(session: Session = Depends(get_db), _: User = Depends(HR)):
    return [collection_service.hr_view(session, item.id) for item in collection_service.list_collections(session)]


@router.post("/collections")
def create_collection(body: CollectionIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    collection = collection_service.create_collection(
        session,
        employee_id=body.employee_id,
        title=body.title,
        description=body.description,
        deadline=body.deadline,
        scope=body.scope,
        actor_id=user.id,
    )
    return collection_service.hr_view(session, collection.id)


@router.get("/collections/{collection_id}")
def get_collection(collection_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    return collection_service.hr_view(session, UUID(collection_id))


@router.patch("/collections/{collection_id}")
def patch_collection(collection_id: str, body: CollectionPatch, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    collection_service.update_collection(session, UUID(collection_id), body.model_dump(exclude_unset=True), user.id)
    return collection_service.hr_view(session, UUID(collection_id))


@router.post("/collections/{collection_id}/open")
def open_collection(collection_id: str, session: Session = Depends(get_db), sender=Depends(get_sender), user: User = Depends(HR)):
    from uuid import UUID

    collection = collection_service.open_collection(session, UUID(collection_id), sender, user.id)
    return collection_service.hr_view(session, collection.id)


@router.post("/collections/{collection_id}/close")
def close_collection(collection_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    collection = collection_service.close_collection(session, UUID(collection_id), user.id)
    return collection_service.hr_view(session, collection.id)


@router.post("/collections/{collection_id}/cancel")
def cancel_collection(collection_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    collection = collection_service.cancel_collection(session, UUID(collection_id), user.id)
    return collection_service.hr_view(session, collection.id)


@router.post("/collections/participants/{participant_id}/confirm")
def confirm_payment(participant_id: str, body: ConfirmIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    participant = collection_service.confirm_payment(session, UUID(participant_id), user.id, body.amount)
    return collection_service.hr_view(session, participant.collection_id)


@router.get("/announcements")
def announcements(session: Session = Depends(get_db), _: User = Depends(HR)):
    return [_announcement_json(item) for item in announcement_service.list_announcements(session)]


@router.post("/announcements")
def create_announcement(body: AnnouncementIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    item = announcement_service.create_announcement(
        session,
        title=body.title,
        body=body.body,
        type=body.type,
        segment=body.segment,
        requires_rsvp=body.requires_rsvp,
        image_url=body.image_url,
        document_url=body.document_url,
        actor_id=user.id,
    )
    return _announcement_json(item)


@router.get("/announcements/{announcement_id}")
def get_announcement(announcement_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    return _announcement_json(announcement_service.get_announcement(session, UUID(announcement_id)))


@router.patch("/announcements/{announcement_id}")
def patch_announcement(announcement_id: str, body: AnnouncementPatch, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    item = announcement_service.update_announcement(session, UUID(announcement_id), body.model_dump(exclude_unset=True), user.id)
    return _announcement_json(item)


@router.post("/announcements/{announcement_id}/preview")
def preview_announcement(announcement_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    return announcement_service.preview(session, UUID(announcement_id))


@router.post("/announcements/{announcement_id}/schedule")
def schedule_announcement(announcement_id: str, body: ScheduleIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    item = announcement_service.schedule_announcement(session, UUID(announcement_id), body.scheduled_for, user.id)
    return _announcement_json(item)


@router.post("/announcements/{announcement_id}/send")
def send_announcement(announcement_id: str, session: Session = Depends(get_db), sender=Depends(get_sender), user: User = Depends(HR)):
    from uuid import UUID

    identifier = UUID(announcement_id)
    item = announcement_service.get_announcement(session, identifier)
    if item.status == "draft":
        item = announcement_service.schedule_announcement(session, identifier, datetime.now(timezone.utc), user.id)
    announcement_service.dispatch_announcement(session, item.id, sender)
    return announcement_service.stats(session, item.id)


@router.post("/announcements/{announcement_id}/cancel")
def cancel_announcement(announcement_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    return _announcement_json(announcement_service.cancel_announcement(session, UUID(announcement_id), user.id))


@router.get("/announcements/{announcement_id}/stats")
def announcement_stats(announcement_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    return announcement_service.stats(session, UUID(announcement_id))


@router.get("/ai/drafts")
def ai_drafts(session: Session = Depends(get_db), _: User = Depends(HR)):
    return [_draft_json(item) for item in ai_service.list_drafts(session)]


@router.post("/ai/drafts")
def create_ai_draft(body: AiDraftIn, session: Session = Depends(get_db), user: User = Depends(HR)):
    llm, model = _llm(session)
    draft = ai_service.create_draft(
        session,
        task=body.task,
        actor_id=user.id,
        llm=llm,
        model_name=model,
        instruction=body.instruction,
        employee_id=body.employee_id,
        style=body.style,
        title=body.title,
        announcement_type=body.announcement_type,
        audience_label=body.audience_label,
        current_text=body.current_text,
        budget_amount=body.budget_amount,
        currency=body.currency,
        deadline=body.deadline,
    )
    return _draft_json(draft)


@router.get("/ai/drafts/{draft_id}")
def get_ai_draft(draft_id: str, session: Session = Depends(get_db), _: User = Depends(HR)):
    from uuid import UUID

    return _draft_json(ai_service.get_draft(session, UUID(draft_id)))


@router.post("/ai/drafts/{draft_id}/approve")
def approve_ai_draft(draft_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    return _draft_json(ai_service.approve_draft(session, UUID(draft_id), user.id))


@router.post("/ai/drafts/{draft_id}/reject")
def reject_ai_draft(draft_id: str, session: Session = Depends(get_db), user: User = Depends(HR)):
    from uuid import UUID

    return _draft_json(ai_service.reject_draft(session, UUID(draft_id), user.id))


@router.get("/settings")
def settings(session: Session = Depends(get_db), _: User = Depends(HR)):
    return _org_json(org_service.get_org(session))


@router.patch("/settings")
def patch_settings(body: SettingsPatch, session: Session = Depends(get_db), user: User = Depends(SUPER)):
    org = org_service.update_organization(session, user.id, body.model_dump(exclude_unset=True))
    return _org_json(org)


@router.get("/admins")
def admins(session: Session = Depends(get_db), _: User = Depends(SUPER)):
    return [_user_json(item) for item in org_service.list_admins(session)]


@router.post("/admins")
def create_admin(body: AdminIn, session: Session = Depends(get_db), user: User = Depends(SUPER)):
    created = org_service.create_admin(session, user.id, body.email, body.password, body.full_name, body.role)
    return _user_json(created)


@router.patch("/admins/{user_id}")
def patch_admin(user_id: str, body: AdminPatch, session: Session = Depends(get_db), user: User = Depends(SUPER)):
    from uuid import UUID

    updated = org_service.update_admin(session, user.id, UUID(user_id), role=body.role, is_active=body.is_active)
    return _user_json(updated)


@router.get("/audit")
def audit(session: Session = Depends(get_db), _: User = Depends(HR)):
    rows = session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200))
    return [
        {
            "id": str(item.id),
            "actor_user_id": str(item.actor_user_id) if item.actor_user_id else None,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "payload": item.payload,
            "created_at": iso(item.created_at),
        }
        for item in rows
    ]


@router.post("/jobs/run-due")
def jobs(session: Session = Depends(get_db), sender=Depends(get_sender), _: User = Depends(SUPER)):
    return run_due(session, sender)


def _input(body: EmployeeIn) -> EmployeeInput:
    return EmployeeInput(**body.model_dump())


def _llm(session: Session):
    settings = get_settings()
    org = org_service.get_org(session)
    return build_llm(org.llm_provider, org.llm_model_name, settings.openai_api_key, settings.llm_base_url)


def _greeting_json(greeting, employee: Employee | None) -> dict:
    return {
        "id": str(greeting.id),
        "employee_id": str(greeting.employee_id),
        "preferred_name": employee.preferred_name if employee else "",
        "full_name": employee.full_name if employee else "",
        "occasion_date": greeting.occasion_date.isoformat(),
        "status": greeting.status,
        "text": greeting.text,
        "scheduled_for": iso(greeting.scheduled_for),
        "sent_at": iso(greeting.sent_at),
        "provider": greeting.provider,
        "failure_reason": greeting.failure_reason,
        "public_greeting_consent": employee.public_greeting_consent if employee else False,
    }


def _announcement_json(item) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "body": item.body,
        "type": item.type,
        "image_url": item.image_url,
        "document_url": item.document_url,
        "status": item.status,
        "scheduled_for": iso(item.scheduled_for),
        "requires_rsvp": item.requires_rsvp,
        "segment": item.segment,
    }


def _draft_json(item) -> dict:
    response = item.response or {}
    return {
        "id": str(item.id),
        "task": item.task,
        "status": item.status,
        "instruction": item.instruction,
        "request_fields": item.request_fields,
        "received_fields": response.get("received_fields") or [],
        "text": response.get("text"),
        "data": response.get("data") or {},
        "provider": item.provider,
        "model_name": item.model_name,
        "greeting_id": str(item.greeting_id) if item.greeting_id else None,
        "collection_id": str(item.collection_id) if item.collection_id else None,
        "announcement_id": str(item.announcement_id) if item.announcement_id else None,
        "executed": False,
    }


def _org_json(org) -> dict:
    return {
        "id": str(org.id),
        "name": org.name,
        "timezone": org.timezone,
        "corporate_chat_id": org.corporate_chat_id,
        "corporate_chat_title": org.corporate_chat_title,
        "corporate_chat_type": org.corporate_chat_type,
        "greeting_lead_days": org.greeting_lead_days,
        "greeting_hour": org.greeting_hour,
        "llm_model_name": org.llm_model_name,
        "llm_provider": org.llm_provider,
        "llm_mode": llm_runtime_mode(org.llm_provider, get_settings().openai_api_key),
        "currency": org.currency,
        "payment_method": org.payment_method,
        "payment_phone": org.payment_phone,
        "payment_fixed_amount": f"{org.payment_fixed_amount:.2f}",
        "payment_details": payment_details_text(org.payment_phone),
        "notion_database_id": org.notion_database_id,
        "notion_database_title": org.notion_database_title,
        "notion_database_type": org.notion_database_type,
        "onboarding_files": list(org.onboarding_files or []),
        "notion_ready": bool(get_settings().notion_api_key and org.notion_database_id),
        "bot_username": org.bot_username,
        "super_admin_telegram_username": org.super_admin_telegram_username,
        "corporate_chat_configured": org.corporate_chat_id is not None,
    }


def _user_json(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "telegram_username": user.telegram_username,
    }
