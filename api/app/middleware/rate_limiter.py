"""Token bucket rate limiter backed by Redis Lua script.

Uses a token bucket algorithm implemented atomically in Lua to prevent
race conditions on the Redis side. Separate read/write buckets per user.

Key format: rl:{user_id}:{bucket_type}
Bucket types: "read" or "write"
"""
import time
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException

from app.config import Settings, settings
from app.dependencies import CurrentUser, RedisClient
from app.models.user import User

# Lua token bucket script — executed atomically on the Redis server.
#
# KEYS[1] = rate limit key (e.g. "rl:{user_id}:{bucket_type}")
# ARGV[1] = max_tokens (integer capacity of the bucket)
# ARGV[2] = refill_rate (tokens per second, float)
# ARGV[3] = now (current Unix timestamp, float)
#
# Returns: 1 if allowed (token consumed), 0 if rejected (bucket empty)
RATE_LIMIT_LUA = """
local key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Load current bucket state
local data = redis.call('HGETALL', key)
local tokens = max_tokens
local last_refill = now

if #data > 0 then
    for i = 1, #data, 2 do
        if data[i] == 'tokens' then
            tokens = tonumber(data[i+1])
        elseif data[i] == 'last_refill' then
            last_refill = tonumber(data[i+1])
        end
    end
end

-- Refill tokens based on elapsed time
local elapsed = now - last_refill
local new_tokens = tokens + elapsed * refill_rate
if new_tokens > max_tokens then
    new_tokens = max_tokens
end

-- Attempt to consume 1 token
local allowed = 0
if new_tokens >= 1 then
    new_tokens = new_tokens - 1
    allowed = 1
end

-- Persist updated state with 120s TTL (2x the refill window)
redis.call('HSET', key, 'tokens', new_tokens, 'last_refill', now)
redis.call('EXPIRE', key, 120)

return allowed
"""


async def check_rate_limit(
    user: User,
    redis_client: aioredis.Redis,
    bucket_type: str,
    app_settings: Settings,
) -> None:
    """Check and consume a token from the user's rate limit bucket.

    Raises HTTP 429 with Retry-After header if the bucket is empty.

    Args:
        user: Authenticated user (provides the bucket key namespace).
        redis_client: Async Redis client from app.state.
        bucket_type: "read" or "write" — selects the capacity setting.
        app_settings: Application settings for max token values.
    """
    key = f"rl:{user.id}:{bucket_type}"

    if bucket_type == "read":
        max_tokens = app_settings.rate_limit_read_per_minute
    else:
        max_tokens = app_settings.rate_limit_write_per_minute

    # Tokens per second — bucket refills fully in 60 seconds
    refill_rate = max_tokens / 60.0

    allowed = await redis_client.eval(
        RATE_LIMIT_LUA,
        1,  # number of KEYS
        key,
        max_tokens,
        refill_rate,
        time.time(),
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )


def require_read_limit():
    """FastAPI dependency factory for read-path rate limiting."""

    async def _check(
        user: CurrentUser,
        redis_client: RedisClient,
    ) -> None:
        await check_rate_limit(user, redis_client, "read", settings)

    return _check


def require_write_limit():
    """FastAPI dependency factory for write-path rate limiting."""

    async def _check(
        user: CurrentUser,
        redis_client: RedisClient,
    ) -> None:
        await check_rate_limit(user, redis_client, "write", settings)

    return _check


# Annotated type aliases — inject into endpoint signatures for clean DI
ReadRateLimit = Annotated[None, Depends(require_read_limit())]
WriteRateLimit = Annotated[None, Depends(require_write_limit())]
