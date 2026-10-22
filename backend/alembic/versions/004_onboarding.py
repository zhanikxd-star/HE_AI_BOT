"""Sales onboarding fields and the seeded Notion database id."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004_onboarding"
down_revision = "003_payment_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("phone", sa.String(32), nullable=False, server_default=""))
    op.add_column("employees", sa.Column("city", sa.String(120), nullable=False, server_default=""))
    op.add_column(
        "organizations",
        sa.Column(
            "notion_database_id",
            sa.String(64),
            nullable=True,
            server_default="40159421a41f80c1bfd5ce5b06de3213",
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("notion_database_title", sa.String(200), nullable=True, server_default="Document Hub"),
    )
    op.add_column(
        "organizations",
        sa.Column("notion_database_type", sa.String(32), nullable=True, server_default="database"),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "onboarding_files",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_table(
        "onboarding_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("notion_status", sa.String(32), nullable=False),
        sa.Column("notion_error", sa.String(200), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_onboarding_telegram", "onboarding_applications", ["telegram_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_onboarding_telegram", table_name="onboarding_applications")
    op.drop_table("onboarding_applications")
    op.drop_column("organizations", "onboarding_files")
    op.drop_column("organizations", "notion_database_type")
    op.drop_column("organizations", "notion_database_title")
    op.drop_column("organizations", "notion_database_id")
    op.drop_column("employees", "city")
    op.drop_column("employees", "phone")
