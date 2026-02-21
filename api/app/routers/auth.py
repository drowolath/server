"""API key generation and authentication verification endpoints.

POST /api/v1/keys  -- generate a new API key (no auth required)
GET  /api/v1/keys/verify -- verify an existing API key (auth required)
"""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser
from app.models.user import User
from app.schemas.auth import APIKeyCreate, APIKeyResponse

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/keys", response_model=APIKeyResponse, status_code=201)
async def generate_api_key(
    body: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
) -> APIKeyResponse:
    """Generate a new API key and register a user account.

    The raw API key is returned exactly once in this response. Only its
    SHA-256 hash is stored in the database; it cannot be retrieved again.

    If an email is provided and already exists in the database, a 409
    Conflict is returned. On the astronomically unlikely event of a hash
    collision, one automatic retry is performed with a freshly generated key.
    """
    # If email provided, check for existing account
    if body.email:
        result = await db.execute(select(User).where(User.email == body.email))
        if result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

    def _make_user(raw_key: str) -> User:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return User(
            api_key_hash=key_hash,
            email=body.email,
            display_name=body.display_name,
        )

    raw_key = secrets.token_urlsafe(32)
    user = _make_user(raw_key)
    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        # Hash collision on api_key_hash (astronomically unlikely) — retry once
        await db.rollback()
        raw_key = secrets.token_urlsafe(32)
        user = _make_user(raw_key)
        db.add(user)
        await db.commit()

    await db.refresh(user)

    return APIKeyResponse(
        api_key=raw_key,
        user_id=user.id,
    )


@router.get("/keys/verify")
async def verify_api_key(user: CurrentUser) -> dict:
    """Verify that the provided API key is valid.

    Returns the authenticated user's ID. Primarily for testing that
    authentication is functioning correctly.
    """
    return {"valid": True, "user_id": str(user.id)}
