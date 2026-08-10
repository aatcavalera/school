"""Add upstream year id and normalized real attendance.

Revision ID: 0003_real_attendance
Revises: 0002_multitenant_sync_foundation
"""

import sqlalchemy as sa
from alembic import op

from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0003_real_attendance"
down_revision = "0002_multitenant_sync_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("school_years_source")}
    if "source_id" not in columns:
        op.add_column("school_years_source", sa.Column("source_id", sa.String(length=32), nullable=True))
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    pass
