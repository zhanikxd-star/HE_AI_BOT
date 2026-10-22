"""Public org defaults. Corporate chat id stays nullable."""

from alembic import op
import sqlalchemy as sa

revision = "002_org_defaults"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("corporate_chat_title", sa.String(200), nullable=True))
    op.add_column("organizations", sa.Column("corporate_chat_type", sa.String(32), nullable=True))
    op.add_column("organizations", sa.Column("bot_username", sa.String(64), nullable=True))
    op.add_column("organizations", sa.Column("super_admin_telegram_username", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "telegram_username")
    op.drop_column("organizations", "super_admin_telegram_username")
    op.drop_column("organizations", "bot_username")
    op.drop_column("organizations", "corporate_chat_type")
    op.drop_column("organizations", "corporate_chat_title")
