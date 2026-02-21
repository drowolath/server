from pydantic import BaseModel, Field
from typing import Optional
import uuid
from datetime import datetime


class TraceSearchRequest(BaseModel):
    q: Optional[str] = Field(default=None, max_length=2000, description="Natural language search query (omit for tag-only search)")
    tags: list[str] = Field(default_factory=list, max_length=10, description="Filter by tags (AND semantics — all must match)")
    limit: int = Field(default=10, ge=1, le=50, description="Max results to return")


class TraceSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    context_text: str
    solution_text: str
    trust_score: float
    status: str
    tags: list[str]
    similarity_score: float  # cosine similarity = 1 - distance
    combined_score: float    # trust-weighted final score
    contributor_id: uuid.UUID
    created_at: datetime


class TraceSearchResponse(BaseModel):
    results: list[TraceSearchResult]
    total: int  # number of results returned
    query: Optional[str] = None  # echo back the query (None for tag-only search)
