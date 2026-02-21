"""Vote submission endpoint for traces.

POST /api/v1/traces/{trace_id}/votes -- cast an up/downvote on a trace
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession, RequireEmail
from app.middleware.rate_limiter import WriteRateLimit
from app.models.tag import Tag, trace_tags
from app.models.trace import Trace
from app.models.vote import Vote
from app.schemas.vote import VoteCreate, VoteResponse
from app.services.trust import (
    apply_vote_to_trace,
    get_vote_weight_for_trace,
    update_contributor_domain_reputation,
)

router = APIRouter(prefix="/api/v1", tags=["votes"])


@router.post(
    "/traces/{trace_id}/votes",
    response_model=VoteResponse,
    status_code=201,
)
async def cast_vote(
    trace_id: uuid.UUID,
    body: VoteCreate,
    user: RequireEmail,
    db: DbSession,
    _rate: WriteRateLimit,
) -> VoteResponse:
    """Cast an upvote or downvote on a trace.

    Validation rules enforced:
    - Trace must exist (404 if not found)
    - Cannot vote on your own trace (403)
    - Cannot vote twice on the same trace (409 — enforced by DB unique constraint)
    - Downvote must include a feedback_tag from the approved set (422 — enforced
      by VoteCreate schema model_validator before this function is called)

    After a successful vote, the trace trust score and confirmation count are
    updated atomically, and the trace may be promoted from pending to validated.
    """
    # Verify trace exists
    result = await db.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Fetch trace tags for domain reputation lookup
    tag_result = await db.execute(
        select(Tag.name)
        .join(trace_tags, Tag.id == trace_tags.c.tag_id)
        .where(trace_tags.c.trace_id == trace_id)
    )
    tag_names = [row[0] for row in tag_result.fetchall()]

    # Prevent self-vote
    if trace.contributor_id == user.id:
        raise HTTPException(status_code=403, detail="Cannot vote on your own trace")

    # Build context_json — stores feedback_tag for downvotes
    context_json = None
    if body.feedback_tag:
        context_json = {"feedback_tag": body.feedback_tag}

    # Create the vote row
    vote = Vote(
        trace_id=trace_id,
        voter_id=user.id,
        vote_type=body.vote_type,
        feedback_text=body.feedback_text,
        context_json=context_json,
    )
    db.add(vote)

    try:
        await db.flush()
    except IntegrityError as exc:
        # Check if the constraint is the duplicate-vote unique constraint
        await db.rollback()
        constraint_name = "uq_votes_trace_id_voter_id"
        if constraint_name in str(exc.orig):
            raise HTTPException(
                status_code=409, detail="Already voted on this trace"
            )
        raise

    # Domain-aware vote weight — uses voter's reputation in trace's domains
    vote_weight = await get_vote_weight_for_trace(
        db=db, voter_id=user.id, trace_tags=tag_names,
    )

    # Apply vote to trace trust score — atomic column-expression UPDATE
    await apply_vote_to_trace(
        db=db,
        trace_id=trace_id,
        vote_weight=vote_weight,
        is_upvote=(body.vote_type == "up"),
    )

    # Update trace contributor's per-domain reputation
    await update_contributor_domain_reputation(
        db=db,
        contributor_id=trace.contributor_id,
        domain_tags=tag_names,
        is_upvote=(body.vote_type == "up"),
    )

    await db.commit()
    await db.refresh(vote)

    # Map context_json feedback_tag back to VoteResponse field
    feedback_tag_value = None
    if vote.context_json:
        feedback_tag_value = vote.context_json.get("feedback_tag")

    return VoteResponse(
        id=vote.id,
        trace_id=vote.trace_id,
        voter_id=vote.voter_id,
        vote_type=vote.vote_type,
        feedback_tag=feedback_tag_value,
        feedback_text=vote.feedback_text,
        created_at=vote.created_at,
    )
