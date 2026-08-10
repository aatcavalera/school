"""Register the existing attendance dashboard schema.

Revision ID: 0001_existing_schema_baseline
Revises:
"""

from alembic import op

from app.db import Base
from app import models  # noqa: F401

revision = "0001_existing_schema_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # checkfirst keeps this baseline safe for the database that predates Alembic,
    # while still allowing a brand-new database to bootstrap from the same image.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # The baseline represents pre-existing production data. Dropping it from a
    # migration would be unsafe, so rollback intentionally preserves the tables.
    pass
