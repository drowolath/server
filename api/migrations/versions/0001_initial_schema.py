"""Initial schema — all tables and HNSW index

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20 00:01:00.000000

Creates all 5 tables: users, traces, votes, tags, trace_tags.
Creates HNSW index on traces.embedding using vector_cosine_ops (matches Phase 3 cosine similarity queries).
Creates B-tree indexes for common query patterns.

NOTE: Written manually (not via autogenerate) because:
  1. Alembic autogenerate cannot generate HNSW index DDL
  2. autogenerate cannot handle Vector(1536) without custom type comparison
  3. Manual migration is more reliable and reviewable for initial schema
"""
from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users table ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("api_key_hash", sa.String(255), nullable=True, unique=True),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("reputation_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- traces table ---
    op.create_table(
        "traces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=False),
        sa.Column("solution_text", sa.Text(), nullable=False),
        # Vector embedding — nullable until background worker processes it
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("embedding_model_id", sa.String(100), nullable=True),
        sa.Column("embedding_model_version", sa.String(100), nullable=True),
        # Trust state machine
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confirmation_count", sa.Integer(), nullable=False, server_default="0"),
        # Contributor link
        sa.Column(
            "contributor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_traces_contributor_id_users"),
            nullable=False,
        ),
        # Agent metadata
        sa.Column("agent_model", sa.String(100), nullable=True),
        sa.Column("agent_version", sa.String(50), nullable=True),
        # Open-ended metadata (domain-agnostic)
        sa.Column("metadata_json", JSON, nullable=True),
        # Seed flag
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # B-tree indexes on traces for common query patterns
    op.create_index("ix_traces_status", "traces", ["status"])
    op.create_index("ix_traces_contributor_id", "traces", ["contributor_id"])
    op.create_index("ix_traces_created_at", "traces", ["created_at"])

    # HNSW index on traces.embedding for cosine similarity search (Phase 3)
    # Uses vector_cosine_ops — matches cosine distance queries in Phase 3 semantic search
    # m=16, ef_construction=64 are sensible defaults for production quality
    op.execute(
        """
        CREATE INDEX ix_traces_embedding_hnsw
        ON traces
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # --- votes table ---
    op.create_table(
        "votes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("traces.id", name="fk_votes_trace_id_traces"),
            nullable=False,
        ),
        sa.Column(
            "voter_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_votes_voter_id_users"),
            nullable=False,
        ),
        sa.Column("vote_type", sa.String(10), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("context_json", JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("trace_id", "voter_id", name="uq_votes_trace_id_voter_id"),
    )

    # --- tags table ---
    op.create_table(
        "tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("is_curated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # B-tree index on tags.name for fast tag lookups
    op.create_index("ix_tags_name", "tags", ["name"])

    # --- trace_tags join table ---
    op.create_table(
        "trace_tags",
        sa.Column(
            "trace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("traces.id", name="fk_trace_tags_trace_id_traces"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tags.id", name="fk_trace_tags_tag_id_tags"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("trace_tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
    op.drop_table("votes")
    op.execute("DROP INDEX IF EXISTS ix_traces_embedding_hnsw")
    op.drop_index("ix_traces_created_at", table_name="traces")
    op.drop_index("ix_traces_contributor_id", table_name="traces")
    op.drop_index("ix_traces_status", table_name="traces")
    op.drop_table("traces")
    op.drop_table("users")
