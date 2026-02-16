"""add huddle support columns

Revision ID: c3a9f2e81d4b
Revises: b21785dd743e
Create Date: 2026-02-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c3a9f2e81d4b"
down_revision = "b21785dd743e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("participants", postgresql.ARRAY(sa.String), nullable=True))
    op.create_index("ix_decisions_participants", "decisions", ["participants"], postgresql_using="gin")
    op.add_column("raw_messages", sa.Column("source_hint", sa.String, nullable=True))


def downgrade() -> None:
    op.drop_column("raw_messages", "source_hint")
    op.drop_index("ix_decisions_participants", table_name="decisions")
    op.drop_column("decisions", "participants")
