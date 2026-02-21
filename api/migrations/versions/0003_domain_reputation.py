"""Contributor domain reputation table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-20 00:03:00.000000

Creates contributor_domain_reputation table to track per-contributor,
per-domain-tag vote counts and Wilson score lower bound.
Written manually (not via autogenerate) consistent with project migration policy.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contributor_domain_reputation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contributor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_cdr_contributor_id_users"),
            nullable=False,
        ),
        sa.Column("domain_tag", sa.String(50), nullable=False),
        sa.Column(
            "upvote_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "downvote_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "wilson_score",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "contributor_id",
            "domain_tag",
            name="uq_contributor_domain_reputation_contributor_domain",
        ),
    )

    # Indexes for common lookup patterns
    op.create_index(
        "ix_cdr_contributor_id",
        "contributor_domain_reputation",
        ["contributor_id"],
    )
    op.create_index(
        "ix_cdr_domain_tag",
        "contributor_domain_reputation",
        ["domain_tag"],
    )


def downgrade() -> None:
    # Drop indexes before table
    op.drop_index("ix_cdr_domain_tag", table_name="contributor_domain_reputation")
    op.drop_index("ix_cdr_contributor_id", table_name="contributor_domain_reputation")
    op.drop_table("contributor_domain_reputation")
