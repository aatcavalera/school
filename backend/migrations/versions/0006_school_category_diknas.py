"""Add school category, per-school late cutoff, and diknas scope table.

Revision ID: 0006_school_category_diknas
Revises: 0005_gender_overrides
"""

import sqlalchemy as sa
from alembic import op
from app.db import Base
from app import models, models_multitenant  # noqa: F401

revision = "0006_school_category_diknas"
down_revision = "0005_gender_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `schools` already exists (from an earlier migration) - create_all only
    # creates missing tables, it does not add columns to existing ones.
    op.add_column("schools", sa.Column("category", sa.String(16), nullable=True))
    op.add_column("schools", sa.Column("school_start_time", sa.String(5), nullable=True))
    op.add_column("schools", sa.Column("late_cutoff_time", sa.String(5), nullable=True))
    op.create_index("ix_schools_category", "schools", ["category"])
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("user_diknas_scopes")
    op.drop_index("ix_schools_category", table_name="schools")
    op.drop_column("schools", "category")
    op.drop_column("schools", "school_start_time")
    op.drop_column("schools", "late_cutoff_time")
