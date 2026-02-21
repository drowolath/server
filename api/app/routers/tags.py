"""Tags listing endpoint.

GET /api/v1/tags -- return all distinct tag names from the database.
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import ReadRateLimit
from app.models.tag import Tag

router = APIRouter(prefix="/api/v1", tags=["tags"])


@router.get("/tags")
async def list_tags(
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> dict:
    """Return all distinct tag names from the database, sorted alphabetically.

    Returns:
        {"tags": ["fastapi", "python", "react", ...]}
    """
    result = await db.execute(select(Tag.name).order_by(Tag.name))
    tag_names = list(result.scalars().all())
    return {"tags": tag_names}
