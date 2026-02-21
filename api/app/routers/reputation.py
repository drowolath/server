"""Contributor reputation endpoint.

GET /api/v1/contributors/{user_id}/reputation -- overall + per-domain breakdown
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import ReadRateLimit
from app.models.reputation import ContributorDomainReputation
from app.models.user import User
from app.schemas.reputation import DomainReputationItem, ReputationResponse

router = APIRouter(prefix="/api/v1", tags=["reputation"])


@router.get(
    "/contributors/{user_id}/reputation",
    response_model=ReputationResponse,
)
async def get_contributor_reputation(
    user_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> ReputationResponse:
    """Get a contributor's overall reputation and per-domain breakdown.

    Returns the aggregate Wilson score (from users.reputation_score) and
    a list of per-domain reputation items ordered by Wilson score descending.

    Any authenticated user can query any contributor's reputation.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    contributor = result.scalar_one_or_none()
    if contributor is None:
        raise HTTPException(status_code=404, detail="Contributor not found")

    domain_result = await db.execute(
        select(ContributorDomainReputation)
        .where(ContributorDomainReputation.contributor_id == user_id)
        .order_by(ContributorDomainReputation.wilson_score.desc())
    )
    domain_rows = domain_result.scalars().all()

    return ReputationResponse(
        user_id=contributor.id,
        overall_wilson_score=contributor.reputation_score,
        domains=[
            DomainReputationItem(
                domain_tag=row.domain_tag,
                wilson_score=row.wilson_score,
                upvote_count=row.upvote_count,
                downvote_count=row.downvote_count,
            )
            for row in domain_rows
        ],
    )
