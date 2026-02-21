"""Pydantic schemas for API key management and authentication."""

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """Request schema for creating a new API key / user registration."""

    email: Optional[str] = Field(None, max_length=255)
    display_name: Optional[str] = Field(None, max_length=100)


class APIKeyResponse(BaseModel):
    """Response schema after a new API key is generated.

    The api_key is shown exactly once. It is stored only as a hash in the
    database and cannot be retrieved again after this response.
    """

    api_key: str
    user_id: uuid.UUID
    message: str = "Store this key securely -- it cannot be retrieved again"
