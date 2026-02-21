"""ContributorDomainReputation ORM model.

Tracks per-contributor, per-domain-tag reputation derived from vote outcomes.
The wilson_score field stores the 95% Wilson score lower bound, computed by
trust.wilson_score_lower_bound(upvote_count, upvote_count + downvote_count).

The unique constraint on (contributor_id, domain_tag) enforces one row per
contributor+domain pair. Upsert logic should reference CDR_UNIQUE_CONSTRAINT
to avoid hardcoding the constraint name (pitfall 4 from REPU research).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import User

# Module-level constant for upsert code (avoids hardcoding constraint name)
CDR_UNIQUE_CONSTRAINT = "uq_contributor_domain_reputation_contributor_domain"


class ContributorDomainReputation(Base):
    """Per-contributor, per-domain reputation row.

    One row per (contributor, domain_tag) pair. Updated atomically on each
    vote cast against a trace in that domain. The wilson_score is recomputed
    in the same transaction as the vote.
    """

    __tablename__ = "contributor_domain_reputation"

    __table_args__ = (
        UniqueConstraint(
            "contributor_id",
            "domain_tag",
            name=CDR_UNIQUE_CONSTRAINT,
        ),
        Index("ix_cdr_contributor_id", "contributor_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_cdr_contributor_id_users"),
        nullable=False,
    )
    domain_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    upvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    downvote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wilson_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship — lazy="raise" prevents implicit loading in async context
    contributor: Mapped["User"] = relationship(
        "User",
        lazy="raise",
        foreign_keys=[contributor_id],
    )
