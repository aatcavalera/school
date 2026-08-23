"""Add synced_class_attendances table (per-session teaching attendance).

Revision ID: 0007_class_attendances
Revises: 0006_school_category_diknas
"""

from alembic import op
from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0007_class_attendances"
down_revision = "0006_school_category_diknas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("synced_class_attendances")
