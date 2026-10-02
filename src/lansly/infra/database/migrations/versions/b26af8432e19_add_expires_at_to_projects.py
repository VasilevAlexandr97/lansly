"""Add expires_at to projects."""

import sqlalchemy as sa

from alembic import op

revision = "b26af8432e19"
down_revision = "4954dd453ffa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "expires_at")
