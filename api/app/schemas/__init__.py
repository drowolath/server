"""CommonTrace Pydantic schemas package.

Re-exports all request and response schemas for convenient importing:

    from app.schemas import TraceCreate, TraceResponse, VoteCreate, ...
"""

from app.schemas.amendment import AmendmentCreate, AmendmentResponse
from app.schemas.auth import APIKeyCreate, APIKeyResponse
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.trace import TraceAccepted, TraceCreate, TraceResponse
from app.schemas.vote import DOWNVOTE_REQUIRED_TAGS, VoteCreate, VoteResponse

__all__ = [
    # Trace
    "TraceCreate",
    "TraceResponse",
    "TraceAccepted",
    # Vote
    "VoteCreate",
    "VoteResponse",
    "DOWNVOTE_REQUIRED_TAGS",
    # Amendment
    "AmendmentCreate",
    "AmendmentResponse",
    # Auth
    "APIKeyCreate",
    "APIKeyResponse",
    # Common
    "ErrorResponse",
    "PaginatedResponse",
]
