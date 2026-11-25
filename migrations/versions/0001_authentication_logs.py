"""Add administrator authentication audit log.

Revision ID: 0001_authentication_logs
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_authentication_logs"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "prospects"
TABLE = "authentication_logs"


def upgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE, schema=SCHEMA):
        return

    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("administrator_name", sa.String(length=120), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_prospects_authentication_logs_email",
        TABLE,
        ["email"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_index(
        "ix_prospects_authentication_logs_event_type",
        TABLE,
        ["event_type"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    if inspect(op.get_bind()).has_table(TABLE, schema=SCHEMA):
        op.drop_table(TABLE, schema=SCHEMA)
