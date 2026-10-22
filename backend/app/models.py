"""Persistence models. Schema is owned by Alembic migrations."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Организация")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Almaty")
    corporate_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    greeting_lead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    greeting_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    llm_model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="gpt-4o-mini")
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KZT")
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False, default="kaspi_phone")
    payment_phone: Mapped[str] = mapped_column(String(32), nullable=False, default="+77029994897")
    payment_fixed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("5000.00"))
    corporate_chat_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    corporate_chat_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    super_admin_telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notion_database_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default="40159421a41f80c1bfd5ce5b06de3213")
    notion_database_title: Mapped[str | None] = mapped_column(String(200), nullable=True, default="Document Hub")
    notion_database_type: Mapped[str | None] = mapped_column(String(32), nullable=True, default="database")
    onboarding_files: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: [])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    preferred_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    position: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hired_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    public_greeting_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notification_settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {"announcements": True, "collections": True})
    participate_in_collections: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invite_token: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    bot_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    department: Mapped[Department | None] = relationship()


Index("uq_employees_telegram_username_lower", func.lower(Employee.telegram_username), unique=True)


class OnboardingApplication(Base):
    __tablename__ = "onboarding_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    step: Mapped[str] = mapped_column(String(32), nullable=False, default="full_name")
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {})
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    notion_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    notion_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class HrBirthdayNotice(Base):
    __tablename__ = "hr_birthday_notices"
    __table_args__ = (UniqueConstraint("employee_id", "occasion_date", name="uq_notice_employee_occasion"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    occasion_date: Mapped[date] = mapped_column(Date, nullable=False)
    alerts_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    employee: Mapped[Employee] = relationship()


class Greeting(Base):
    __tablename__ = "greetings"
    __table_args__ = (UniqueConstraint("employee_id", "occasion_date", name="uq_greeting_employee_occasion"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    occasion_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_approval")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    employee: Mapped[Employee] = relationship()


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contribution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    fixed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KZT")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payment_details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    employee: Mapped[Employee] = relationship()
    participants: Mapped[list[CollectionParticipant]] = relationship(back_populates="collection")


class CollectionParticipant(Base):
    __tablename__ = "collection_participants"
    __table_args__ = (UniqueConstraint("collection_id", "employee_id", name="uq_collection_participant"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="invited")
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    collection: Mapped[Collection] = relationship(back_populates="participants")
    employee: Mapped[Employee] = relationship()


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requires_rsvp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    segment: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    deliveries: Mapped[list[AnnouncementDelivery]] = relationship(back_populates="announcement")


class AnnouncementDelivery(Base):
    __tablename__ = "announcement_deliveries"
    __table_args__ = (UniqueConstraint("announcement_id", "employee_id", name="uq_announcement_delivery"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    announcement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("announcements.id"), nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    rsvp_status: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    announcement: Mapped[Announcement] = relationship(back_populates="deliveries")
    employee: Mapped[Employee] = relationship()


class ScheduledAction(Base):
    __tablename__ = "scheduled_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiDraft(Base):
    __tablename__ = "ai_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    greeting_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("greetings.id"), nullable=True)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"), nullable=True)
    announcement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("announcements.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
