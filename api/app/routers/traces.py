"""Trace submission and retrieval endpoints.

POST /api/v1/traces      -- submit a new trace (auth + rate limit + PII scan)
GET  /api/v1/traces/{id} -- retrieve a trace with its tags
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import insert, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DbSession, RequireEmail
from app.middleware.rate_limiter import ReadRateLimit, WriteRateLimit
from app.models.tag import Tag, trace_tags
from app.models.trace import Trace
from app.schemas.trace import TraceAccepted, TraceCreate, TraceResponse
from app.services.scanner import SecretDetectedError, scan_trace_submission
from app.services.staleness import check_trace_staleness
from app.services.tags import normalize_tag, validate_tag

router = APIRouter(prefix="/api/v1", tags=["traces"])


@router.post("/traces", response_model=TraceAccepted, status_code=202)
async def submit_trace(
    body: TraceCreate,
    user: RequireEmail,
    db: DbSession,
    _rate: WriteRateLimit,
) -> TraceAccepted:
    """Submit a new trace for community validation.

    Passes through three gates before database write:
    1. Authentication (RequireEmail dependency — email required for contributions)
    2. Write rate limit (WriteRateLimit dependency)
    3. PII / secrets scan (scan_trace_submission)

    Tags are normalized, validated, and created if not already present.
    A staleness check is performed on metadata_json library references.

    Returns 202 Accepted with the trace ID in pending state.
    """
    # Gate 3: PII scan — runs synchronously before any DB write
    try:
        scan_trace_submission(body.title, body.context_text, body.solution_text)
    except SecretDetectedError as e:
        raise HTTPException(status_code=422, detail=f"Content rejected: {e}")

    # Create the trace row first (without tags — we'll link them after)
    trace = Trace(
        title=body.title,
        context_text=body.context_text,
        solution_text=body.solution_text,
        agent_model=body.agent_model,
        agent_version=body.agent_version,
        metadata_json=body.metadata_json,
        status="pending",
        contributor_id=user.id,
    )

    # Staleness check — never blocks submission, just sets the flag
    is_stale = await check_trace_staleness(body.metadata_json)
    if is_stale:
        trace.is_stale = True

    db.add(trace)
    # Flush to get trace.id before inserting tag associations
    await db.flush()

    # Tag processing: normalize -> validate -> get-or-create -> associate
    for raw_tag in body.tags:
        normalized = normalize_tag(raw_tag)
        if not validate_tag(normalized):
            # Skip invalid tags silently — schema allows any string input,
            # but we only persist tags that pass normalization + validation
            continue

        # Get or create the Tag row
        result = await db.execute(select(Tag).where(Tag.name == normalized))
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=normalized)
            db.add(tag)
            await db.flush()  # Flush to get tag.id

        # Direct join-table insert (avoids MissingGreenlet from relationship.append)
        await db.execute(
            insert(trace_tags).values(trace_id=trace.id, tag_id=tag.id)
        )

    await db.commit()
    await db.refresh(trace)

    return TraceAccepted(id=trace.id, status="pending")


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(
    trace_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> TraceResponse:
    """Retrieve a trace by ID, including its associated tags.

    Uses selectinload to eager-load the tags relationship and avoid
    MissingGreenlet errors in async context.
    """
    result = await db.execute(
        select(Trace)
        .where(Trace.id == trace_id)
        .options(selectinload(Trace.tags))
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Serialize tags to list of name strings for the response schema
    tag_names = [tag.name for tag in trace.tags]

    return TraceResponse(
        id=trace.id,
        status=trace.status,
        title=trace.title,
        context_text=trace.context_text,
        solution_text=trace.solution_text,
        trust_score=trace.trust_score,
        confirmation_count=trace.confirmation_count,
        tags=tag_names,
        is_stale=trace.is_stale,
        is_flagged=trace.is_flagged,
        contributor_id=trace.contributor_id,
        created_at=trace.created_at,
        updated_at=trace.updated_at,
    )
