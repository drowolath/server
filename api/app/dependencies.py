import hashlib
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

# Existing dependency — keep as-is
DbSession = Annotated[AsyncSession, Depends(get_db)]

# API key security scheme — registers in OpenAPI security definition
api_key_header = APIKeyHeader(name=settings.api_key_header_name, auto_error=True)


async def get_redis(request: Request) -> aioredis.Redis:
    """Inject the Redis client from app.state (set during lifespan startup)."""
    return request.app.state.redis


async def get_current_user(
    raw_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate a request via X-API-Key header.

    Computes SHA-256 hash of the raw key and looks it up in users.api_key_hash.
    Raises 401 for both missing and invalid keys (no distinction — prevents enumeration).
    """
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(select(User).where(User.api_key_hash == key_hash))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


# Annotated type aliases for clean endpoint signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]


async def require_email(user: User = Depends(get_current_user)) -> User:
    """Gate: requires authenticated user to have a registered email.

    Raises 403 if user.email is None. Implements identity cost (REPU-02):
    anonymous API key usage cannot submit contributions.
    Applied to write paths only — NOT to POST /api/v1/keys or GET endpoints.
    """
    if user.email is None:
        raise HTTPException(
            status_code=403,
            detail="Email registration required to submit contributions. "
                   "Re-register with POST /api/v1/keys providing an email address.",
        )
    return user


RequireEmail = Annotated[User, Depends(require_email)]
