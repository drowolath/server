"""Pydantic schemas for trace amendments."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AmendmentCreate(BaseModel):
    """Request schema for submitting an amendment to a trace."""

    improved_solution: str = Field(min_length=1)
    explanation: str = Field(min_length=1, max_length=5000)


class AmendmentResponse(BaseModel):
    """Response schema for an amendment, suitable for ORM serialization."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_trace_id: uuid.UUID
    submitter_id: uuid.UUID
    improved_solution: str
    explanation: str
    created_at: datetime
