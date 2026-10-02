"""Add project version to notifications."""

import sqlalchemy as sa

from alembic import op

revision = "c38d7f19a642"
down_revision = "b26af8432e19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_notifications",
        sa.Column(
            "project_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute("""
        UPDATE project_notifications AS notification
        SET project_updated_at = project.updated_at
        FROM projects AS project
        WHERE notification.project_id = project.id
    """)
    op.alter_column(
        "project_notifications",
        "project_updated_at",
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("project_notifications", "project_updated_at")
