import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .trace import Trace
    from .user import User


class Amendment(Base):
    __tablename__ = "amendments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    original_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("traces.id", name="fk_amendments_original_trace_id_traces"),
        nullable=False,
        index=True,
    )
    submitter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_amendments_submitter_id_users"),
        nullable=False,
        index=True,
    )
    improved_solution: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships — lazy="raise" to prevent accidental N+1 queries
    original_trace: Mapped["Trace"] = relationship(
        "Trace", lazy="raise", foreign_keys=[original_trace_id]
    )
    submitter: Mapped["User"] = relationship(
        "User", lazy="raise", foreign_keys=[submitter_id]
    )
