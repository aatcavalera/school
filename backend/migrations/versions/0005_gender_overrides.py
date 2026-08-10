"""Add gender_overrides table for manual admin corrections.

Revision ID: 0005_gender_overrides
Revises: 0004_dashboard_aggregates
"""

from alembic import op
from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0005_gender_overrides"
down_revision = "0004_dashboard_aggregates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("gender_overrides")
