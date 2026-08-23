"""Add synced_schedules table (jadwal pelajaran).

Revision ID: 0008_schedules
Revises: 0007_class_attendances
"""

from alembic import op
from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0008_schedules"
down_revision = "0007_class_attendances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("synced_schedules")
