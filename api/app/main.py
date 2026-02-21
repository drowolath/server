from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI

from app.config import settings
from app.logging_config import configure_logging
from app.metrics import metrics_endpoint
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.routers import amendments, auth, moderation, reputation, search, tags, traces, votes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure structured logging before anything else
    configure_logging()

    # Startup: create Redis connection and store on app.state
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    try:
        yield
    finally:
        # Shutdown: close Redis connection
        await app.state.redis.aclose()


app = FastAPI(title="CommonTrace API", version="0.1.0", lifespan=lifespan)

# Register request logging middleware (runs on every request)
app.add_middleware(RequestLoggingMiddleware)

# Register all API routers
app.include_router(auth.router)
app.include_router(traces.router)
app.include_router(votes.router)
app.include_router(amendments.router)

# Moderation router (02-04)
app.include_router(moderation.router)

# Search router (03-02)
app.include_router(search.router)

# Reputation router (04-02)
app.include_router(reputation.router)

# Tags router (05-01)
app.include_router(tags.router)

# Prometheus metrics endpoint
app.get("/metrics")(metrics_endpoint)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
