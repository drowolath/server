"""Enable pgvector extension

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-02-20 00:00:00.000000

This MUST be the first migration — pgvector extension must exist before
any migration that creates a column of type Vector(). Creating the extension
first ensures migrations run cleanly on a fresh database.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension — must happen before any Vector() column is created
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
