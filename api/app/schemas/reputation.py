"""Pydantic schemas for reputation read endpoints.

ReputationResponse is the top-level response for GET /api/v1/reputation/{user_id}.
DomainReputationItem represents a single domain-tag reputation row.
"""

import uuid

from pydantic import BaseModel, ConfigDict


class DomainReputationItem(BaseModel):
    domain_tag: str
    wilson_score: float
    upvote_count: int
    downvote_count: int


class ReputationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    overall_wilson_score: float
    domains: list[DomainReputationItem]
