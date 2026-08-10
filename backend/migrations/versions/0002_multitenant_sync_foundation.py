"""Add multi-tenant synchronization foundation.

Revision ID: 0002_multitenant_sync_foundation
Revises: 0001_existing_schema_baseline
"""

from alembic import op

from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0002_multitenant_sync_foundation"
down_revision = "0001_existing_schema_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Production data is intentionally preserved; destructive rollback requires
    # an explicit reviewed migration after a verified backup.
    pass
