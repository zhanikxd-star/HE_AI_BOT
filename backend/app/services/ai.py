"""AI drafts. Approval creates drafts only and never sends or opens a collection."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.rules import guard_llm_fields, occasion_on_or_after, org_local_date
from app.errors import DomainError, NotFoundError
from app.models import AiDraft, Announcement, Collection, Department, Employee, Greeting, utcnow
from app.ports import LlmRequest
from app.services.audit import write_audit
from app.services.org import get_org, payment_details_text

TASKS = {"greeting", "announcement", "collection", "gift_ideas", "nl_command"}


def create_draft(
    session: Session,
    *,
    task: str,
    actor_id: UUID | None,
    llm,
    model_name: str,
    instruction: str = "",
    employee_id: UUID | None = None,
    style: str | None = None,
    title: str | None = None,
    announcement_type: str | None = None,
    audience_label: str | None = None,
    current_text: str | None = None,
    budget_amount: str | None = None,
    currency: str | None = None,
    deadline: str | None = None,
) -> AiDraft:
    if task not in TASKS:
        raise DomainError("Неизвестная задача для ассистента")
    fields = _fields(
        session,
        task=task,
        instruction=instruction,
        employee_id=employee_id,
        style=style,
        title=title,
        announcement_type=announcement_type,
        audience_label=audience_label,
        current_text=current_text,
        budget_amount=budget_amount,
        currency=currency,
        deadline=deadline,
    )
    safe_fields = guard_llm_fields(task, fields)
    response = llm.complete(LlmRequest(task=task, model=model_name, fields=safe_fields, style=style))
    draft = AiDraft(
        task=task,
        status="draft",
        instruction=instruction or "",
        request_fields=safe_fields,
        response={
            "received_fields": response.received_fields,
            "text": response.text,
            "data": response.data,
            "provider": response.provider,
            "model": response.model,
        },
        provider=response.provider,
        model_name=response.model,
        created_by=actor_id,
        created_at=utcnow(),
    )
    session.add(draft)
    write_audit(session, actor_id, "ai.draft", "ai_draft", draft.id, {"task": task, "provider": response.provider})
    session.commit()
    return draft


def approve_draft(session: Session, draft_id: UUID, actor_id: UUID | None) -> AiDraft:
    """Materialise HR-visible drafts. Does not schedule a send or open a collection."""
    draft = _get(session, draft_id)
    if draft.status != "draft":
        raise DomainError("Черновик уже обработан")
    data = (draft.response or {}).get("data") or {}
    if draft.task == "greeting":
        employee = _employee_from_fields(session, draft)
        greeting = _pending_greeting(session, employee, data.get("greeting_text") or draft.response.get("text") or "")
        draft.greeting_id = greeting.id
    elif draft.task == "announcement":
        announcement = _draft_announcement(session, draft, data, actor_id)
        draft.announcement_id = announcement.id
    elif draft.task == "collection":
        employee = _employee_from_fields(session, draft)
        collection = _draft_collection(session, employee, data, actor_id)
        draft.collection_id = collection.id
    elif draft.task == "nl_command":
        _approve_natural(session, draft, data, actor_id)
    elif draft.task == "gift_ideas":
        pass
    draft.status = "approved"
    write_audit(session, actor_id, "ai.approve", "ai_draft", draft.id, {"task": draft.task})
    session.commit()
    return draft


def reject_draft(session: Session, draft_id: UUID, actor_id: UUID | None) -> AiDraft:
    draft = _get(session, draft_id)
    if draft.status != "draft":
        raise DomainError("Черновик уже обработан")
    draft.status = "rejected"
    write_audit(session, actor_id, "ai.reject", "ai_draft", draft.id, {})
    session.commit()
    return draft


def list_drafts(session: Session) -> list[AiDraft]:
    return list(session.scalars(select(AiDraft).order_by(AiDraft.created_at.desc())))


def get_draft(session: Session, draft_id: UUID) -> AiDraft:
    return _get(session, draft_id)


def _approve_natural(session: Session, draft: AiDraft, data: dict, actor_id: UUID | None) -> None:
    intent = data.get("intent") or {}
    employee = _find_preferred(session, intent.get("employee_preferred_name"))
    if employee is None:
        raise DomainError("Сотрудник из запроса не найден. Черновик не исполнен")
    actions = intent.get("actions") or []
    if "greeting" in actions:
        greeting = _pending_greeting(session, employee, data.get("greeting_text") or "")
        draft.greeting_id = greeting.id
    if "collection" in actions and data.get("collection"):
        collection = _draft_collection(session, employee, data["collection"], actor_id)
        draft.collection_id = collection.id


def _pending_greeting(session: Session, employee: Employee, text: str) -> Greeting:
    org = get_org(session)
    today = org_local_date(datetime.now(timezone.utc), org.timezone)
    occasion = occasion_on_or_after(employee.birth_date, today)
    greeting = session.scalar(select(Greeting).where(Greeting.employee_id == employee.id, Greeting.occasion_date == occasion))
    cleaned = (text or "").strip()
    if greeting is None:
        status = "pending_approval" if employee.public_greeting_consent else "skipped_no_consent"
        greeting = Greeting(
            employee_id=employee.id,
            occasion_date=occasion,
            status=status,
            text=cleaned,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(greeting)
        session.flush()
        return greeting
    if greeting.status in {"sent", "simulated", "sending"}:
        return greeting
    if cleaned and greeting.status in {"pending_approval", "draft", "skipped_no_consent", "cancelled", "failed"}:
        greeting.text = cleaned
    if employee.public_greeting_consent and greeting.status in {"draft", "skipped_no_consent", "cancelled", "failed"}:
        greeting.status = "pending_approval"
    elif not employee.public_greeting_consent and greeting.status in {"pending_approval", "draft", "scheduled"}:
        greeting.status = "skipped_no_consent"
    greeting.updated_at = utcnow()
    return greeting


def _draft_collection(session: Session, employee: Employee, data: dict, actor_id: UUID | None) -> Collection:
    org = get_org(session)
    collection = Collection(
        employee_id=employee.id,
        title=str(data.get("title") or f"Сбор — {employee.preferred_name}"),
        description=str(data.get("description") or "Участие добровольное."),
        contribution_mode="fixed",
        fixed_amount=org.payment_fixed_amount,
        currency=(org.currency or "KZT").upper(),
        deadline=None,
        status="draft",
        scope={"all": True, "department_ids": [], "employee_ids": []},
        payment_details=payment_details_text(org.payment_phone),
        created_by=actor_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(collection)
    session.flush()
    return collection


def _draft_announcement(session: Session, draft: AiDraft, data: dict, actor_id: UUID | None) -> Announcement:
    fields = draft.request_fields or {}
    announcement = Announcement(
        title=str(data.get("title") or fields.get("title") or "Объявление"),
        body=str(data.get("body") or draft.response.get("text") or ""),
        type=str(fields.get("announcement_type") or "news"),
        status="draft",
        requires_rsvp=False,
        segment={"all": False, "department_ids": [], "employee_ids": []},
        created_by=actor_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(announcement)
    session.flush()
    return announcement


def _fields(session: Session, **kwargs) -> dict:
    task = kwargs["task"]
    if task == "greeting":
        employee = _must_employee(session, kwargs.get("employee_id"))
        variant = session.scalar(select(func.count()).select_from(Greeting).where(Greeting.employee_id == employee.id)) or 0
        fields = {"preferred_name": employee.preferred_name, "style": kwargs.get("style") or "warm", "variant": int(variant)}
        if employee.position:
            fields["position"] = employee.position
        if employee.department_id:
            department = session.get(Department, employee.department_id)
            if department:
                fields["department"] = department.name
        return fields
    if task == "announcement":
        fields = {
            "title": kwargs.get("title") or "Объявление",
            "announcement_type": kwargs.get("announcement_type") or "news",
            "style": kwargs.get("style") or "friendly",
            "audience_label": kwargs.get("audience_label") or "коллеги",
        }
        if kwargs.get("current_text"):
            fields["current_text"] = kwargs["current_text"]
        return fields
    if task == "collection":
        employee = _must_employee(session, kwargs.get("employee_id"))
        fields = {"preferred_name": employee.preferred_name, "currency": kwargs.get("currency") or "KZT"}
        if kwargs.get("budget_amount"):
            fields["budget_amount"] = str(kwargs["budget_amount"])
        if kwargs.get("deadline"):
            fields["deadline"] = str(kwargs["deadline"])
        return fields
    if task == "gift_ideas":
        employee = _must_employee(session, kwargs.get("employee_id"))
        fields = {"preferred_name": employee.preferred_name, "currency": kwargs.get("currency") or "KZT"}
        if kwargs.get("budget_amount"):
            fields["budget_amount"] = str(kwargs["budget_amount"])
        return fields
    names = [row.preferred_name for row in session.scalars(select(Employee).where(Employee.status == "active"))]
    return {"instruction": kwargs.get("instruction") or "", "candidate_names": names}


def _employee_from_fields(session: Session, draft: AiDraft) -> Employee:
    name = (draft.request_fields or {}).get("preferred_name")
    employee = _find_preferred(session, name)
    if employee is None:
        raise DomainError("Сотрудник для черновика не найден")
    return employee


def _must_employee(session: Session, employee_id: UUID | None) -> Employee:
    if employee_id is None:
        raise DomainError("Укажите сотрудника")
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Сотрудник не найден")
    return employee


def _find_preferred(session: Session, name: str | None) -> Employee | None:
    if not name:
        return None
    for employee in session.scalars(select(Employee).where(Employee.status == "active")):
        if employee.preferred_name.casefold() == name.casefold():
            return employee
    return None


def _get(session: Session, draft_id: UUID) -> AiDraft:
    draft = session.get(AiDraft, draft_id)
    if draft is None:
        raise NotFoundError("Черновик не найден")
    return draft
