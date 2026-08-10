"""Add dashboard read aggregates.

Revision ID: 0004_dashboard_aggregates
Revises: 0003_real_attendance
"""

from alembic import op
from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0004_dashboard_aggregates"
down_revision = "0003_real_attendance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    pass
