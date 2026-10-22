"""Organization payment default for gift collections."""

from alembic import op
import sqlalchemy as sa

revision = "003_payment_defaults"
down_revision = "002_org_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("payment_method", sa.String(32), nullable=False, server_default="kaspi_phone"),
    )
    op.add_column(
        "organizations",
        sa.Column("payment_phone", sa.String(32), nullable=False, server_default="+77029994897"),
    )
    op.add_column(
        "organizations",
        sa.Column("payment_fixed_amount", sa.Numeric(12, 2), nullable=False, server_default="5000"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "payment_fixed_amount")
    op.drop_column("organizations", "payment_phone")
    op.drop_column("organizations", "payment_method")
