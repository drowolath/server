"""Amendment submission endpoint for traces.

POST /api/v1/traces/{trace_id}/amendments -- submit an improved solution
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, RequireEmail
from app.middleware.rate_limiter import WriteRateLimit
from app.models.amendment import Amendment
from app.models.trace import Trace
from app.schemas.amendment import AmendmentCreate, AmendmentResponse
from app.services.scanner import SecretDetectedError, scan_amendment_submission

router = APIRouter(prefix="/api/v1", tags=["amendments"])


@router.post(
    "/traces/{trace_id}/amendments",
    response_model=AmendmentResponse,
    status_code=201,
)
async def submit_amendment(
    trace_id: uuid.UUID,
    body: AmendmentCreate,
    user: RequireEmail,
    db: DbSession,
    _rate: WriteRateLimit,
) -> AmendmentResponse:
    """Submit an amendment to an existing trace.

    An amendment proposes an improved solution and explains why the change
    is better. Both fields are scanned for PII/secrets before storage.

    Validation rules:
    - Trace must exist (404 if not found)
    - Content must not contain secrets (422 from PII scan gate)
    """
    # Verify trace exists
    result = await db.execute(select(Trace).where(Trace.id == trace_id))
    trace = result.scalar_one_or_none()
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    # PII scan gate — runs before any DB write
    try:
        scan_amendment_submission(body.improved_solution, body.explanation)
    except SecretDetectedError as e:
        raise HTTPException(status_code=422, detail=f"Content rejected: {e}")

    # Create the amendment row
    amendment = Amendment(
        original_trace_id=trace_id,
        submitter_id=user.id,
        improved_solution=body.improved_solution,
        explanation=body.explanation,
    )
    db.add(amendment)
    await db.commit()
    await db.refresh(amendment)

    return AmendmentResponse(
        id=amendment.id,
        original_trace_id=amendment.original_trace_id,
        submitter_id=amendment.submitter_id,
        improved_solution=amendment.improved_solution,
        explanation=amendment.explanation,
        created_at=amendment.created_at,
    )
