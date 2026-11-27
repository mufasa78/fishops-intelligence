"""Add organization outreach and follow-up history.

Revision ID: 0002_outreach_activities
Revises: 0001_authentication_logs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_outreach_activities"
down_revision = "0001_authentication_logs"
branch_labels = None
depends_on = None

SCHEMA = "prospects"
TABLE = "outreach_activities"


def upgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE, schema=SCHEMA):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("contact_point_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.Column("next_step_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{SCHEMA}.organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contact_point_id"],
            [f"{SCHEMA}.contact_points.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_prospects_outreach_activities_organization_id",
        TABLE,
        ["organization_id"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE, schema=SCHEMA):
        op.drop_table(TABLE, schema=SCHEMA)
