"""Request bodies."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class DepartmentIn(BaseModel):
    name: str


class EmployeeIn(BaseModel):
    full_name: str
    preferred_name: str
    birth_date: date
    department_id: UUID | None = None
    position: str = ""
    phone: str = ""
    city: str = ""
    telegram_id: int | None = None
    telegram_username: str | None = None
    hired_at: date | None = None
    public_greeting_consent: bool = False
    participate_in_collections: bool = True
    notification_settings: dict | None = None


class EmployeePatch(BaseModel):
    full_name: str | None = None
    preferred_name: str | None = None
    birth_date: date | None = None
    department_id: UUID | None = None
    position: str | None = None
    phone: str | None = None
    city: str | None = None
    telegram_id: int | None = None
    telegram_username: str | None = None
    hired_at: date | None = None
    public_greeting_consent: bool | None = None
    participate_in_collections: bool | None = None
    notification_settings: dict | None = None
    status: str | None = None


class GreetingApproveIn(BaseModel):
    text: str
    scheduled_for: datetime | None = None


class CollectionIn(BaseModel):
    employee_id: UUID
    title: str
    description: str = ""
    deadline: date | None = None
    scope: dict | None = None


class CollectionPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    deadline: date | None = None
    scope: dict | None = None


class ConfirmIn(BaseModel):
    amount: Decimal | None = None


class AnnouncementIn(BaseModel):
    title: str
    body: str = ""
    type: str = "news"
    segment: dict | None = None
    requires_rsvp: bool = False
    image_url: str | None = None
    document_url: str | None = None


class AnnouncementPatch(BaseModel):
    title: str | None = None
    body: str | None = None
    type: str | None = None
    segment: dict | None = None
    requires_rsvp: bool | None = None
    image_url: str | None = None
    document_url: str | None = None


class ScheduleIn(BaseModel):
    scheduled_for: datetime


class AiDraftIn(BaseModel):
    task: str
    instruction: str = ""
    employee_id: UUID | None = None
    style: str | None = None
    title: str | None = None
    announcement_type: str | None = None
    audience_label: str | None = None
    current_text: str | None = None
    budget_amount: str | None = None
    currency: str | None = None
    deadline: str | None = None


class SettingsPatch(BaseModel):
    name: str | None = None
    timezone: str | None = None
    corporate_chat_id: int | None = None
    greeting_lead_days: int | None = None
    greeting_hour: int | None = None
    llm_model_name: str | None = None
    llm_provider: str | None = None
    currency: str | None = None
    payment_phone: str | None = None
    payment_fixed_amount: Decimal | None = None
    notion_database_id: str | None = None
    onboarding_files: list | None = None
    bot_username: str | None = None
    super_admin_telegram_username: str | None = None


class AdminIn(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str
    role: str = "hr_admin"


class AdminPatch(BaseModel):
    role: str | None = None
    is_active: bool | None = None
