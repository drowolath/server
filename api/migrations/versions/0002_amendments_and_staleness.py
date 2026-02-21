"""Amendments table and staleness columns on traces

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-20 00:02:00.000000

Adds staleness/flagging columns to traces table and creates the amendments table.
Written manually (not via autogenerate) consistent with project migration policy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Add staleness/flagging columns to traces ---
    op.add_column(
        "traces",
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "traces",
        sa.Column(
            "is_flagged",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "traces",
        sa.Column(
            "flagged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Indexes for filtering by staleness and flagging status
    op.create_index("ix_traces_is_stale", "traces", ["is_stale"])
    op.create_index("ix_traces_is_flagged", "traces", ["is_flagged"])

    # --- amendments table ---
    op.create_table(
        "amendments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "original_trace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("traces.id", name="fk_amendments_original_trace_id_traces"),
            nullable=False,
        ),
        sa.Column(
            "submitter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_amendments_submitter_id_users"),
            nullable=False,
        ),
        sa.Column("improved_solution", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes for common lookup patterns on amendments
    op.create_index("ix_amendments_original_trace_id", "amendments", ["original_trace_id"])
    op.create_index("ix_amendments_submitter_id", "amendments", ["submitter_id"])


def downgrade() -> None:
    # Drop in reverse order of creation
    op.drop_index("ix_amendments_submitter_id", table_name="amendments")
    op.drop_index("ix_amendments_original_trace_id", table_name="amendments")
    op.drop_table("amendments")

    op.drop_index("ix_traces_is_flagged", table_name="traces")
    op.drop_index("ix_traces_is_stale", table_name="traces")

    op.drop_column("traces", "flagged_at")
    op.drop_column("traces", "is_flagged")
    op.drop_column("traces", "is_stale")
