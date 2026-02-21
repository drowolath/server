import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .trace import Trace
    from .user import User


class VoteType(str, enum.Enum):
    up = "up"
    down = "down"


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("trace_id", "voter_id", name="uq_votes_trace_id_voter_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), nullable=False
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    vote_type: Mapped[str] = mapped_column(String(10), nullable=False)
    feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    trace: Mapped["Trace"] = relationship("Trace", back_populates="votes")
    voter: Mapped["User"] = relationship("User", back_populates="votes")
