import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from .base import Base

if TYPE_CHECKING:
    from .tag import Tag
    from .user import User
    from .vote import Vote


class TraceStatus(str, enum.Enum):
    pending = "pending"
    validated = "validated"


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    context_text: Mapped[str] = mapped_column(Text, nullable=False)
    solution_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Vector embedding — null until background worker processes it
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1536), nullable=True)
    embedding_model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Trust state machine — every trace starts pending (DATA-04)
    status: Mapped[str] = mapped_column(
        String(20), default=TraceStatus.pending, nullable=False
    )
    trust_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confirmation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Contributor link
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Domain-agnostic agent metadata
    agent_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Open-ended metadata (domain-agnostic: language, framework, task type, etc.)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Seed flag — seed traces are auto-validated on import (no confirmation needed)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Staleness and flagging (added in migration 0002)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flagged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    contributor: Mapped["User"] = relationship("User", back_populates="traces")
    votes: Mapped[list["Vote"]] = relationship("Vote", back_populates="trace")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="trace_tags", back_populates="traces"
    )
