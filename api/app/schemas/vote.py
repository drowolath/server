"""Pydantic schemas for voting on traces."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

# Tags that must be provided when submitting a downvote (CONT-02).
# A downvote without a contextual tag is rejected at the schema level.
DOWNVOTE_REQUIRED_TAGS: set[str] = {"outdated", "wrong", "security_concern", "spam"}


class VoteCreate(BaseModel):
    """Request schema for submitting a vote on a trace."""

    vote_type: str  # "up" or "down"
    feedback_tag: Optional[str] = None
    feedback_text: Optional[str] = None

    @model_validator(mode="after")
    def downvote_requires_tag(self) -> "VoteCreate":
        """Enforce that downvotes include an approved contextual tag.

        A downvote without a feedback_tag from DOWNVOTE_REQUIRED_TAGS is
        rejected to ensure actionable feedback accompanies negative votes.
        """
        if self.vote_type not in ("up", "down"):
            raise ValueError("vote_type must be 'up' or 'down'")

        if self.vote_type == "down" and self.feedback_tag not in DOWNVOTE_REQUIRED_TAGS:
            raise ValueError(
                f"A downvote requires a feedback_tag from: {sorted(DOWNVOTE_REQUIRED_TAGS)}"
            )

        return self


class VoteResponse(BaseModel):
    """Response schema for a submitted vote."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: uuid.UUID
    voter_id: uuid.UUID
    vote_type: str
    feedback_tag: Optional[str] = None
    feedback_text: Optional[str] = None
    created_at: datetime
