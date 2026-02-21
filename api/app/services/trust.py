"""Vote application and trust score / trace promotion logic.

This module handles the atomic update of a trace's trust state when a vote
is applied, and promotes traces from 'pending' to 'validated' when the
validation threshold is reached (SAFE-01).

Also provides the Wilson score lower bound formula used for reputation ranking.

Design notes:
- All database updates use column expressions (Trace.column + delta) to
  ensure atomicity — no Python-side read-modify-write that could race.
- Promotion check happens after the UPDATE by re-querying the row. This is
  a separate SELECT + conditional UPDATE, which is safe under the assumption
  that each user can vote only once per trace (enforced by DB unique constraint).
- vote_weight allows future reputation-weighted voting without schema changes.
"""

import math
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.reputation import CDR_UNIQUE_CONSTRAINT, ContributorDomainReputation
from app.models.trace import Trace, TraceStatus
from app.models.user import User


def wilson_score_lower_bound(upvotes: int, total_votes: int) -> float:
    """Compute the 95% Wilson score confidence interval lower bound.

    Returns 0.0 when total_votes == 0 (no data = no confidence).
    Returns a value in [0, 1] representing the lower bound of the true
    positive rate at 95% confidence.

    BASE_WEIGHT context: new contributors with no votes score 0.0.
    An established contributor with 80% upvote rate on 50 votes scores ~0.66.
    This creates a measurable weight difference for REPU-01.

    Source: https://www.evanmiller.org/how-not-to-sort-by-average-rating.html

    Args:
        upvotes: Number of positive votes.
        total_votes: Total votes (upvotes + downvotes).

    Returns:
        Wilson score lower bound in [0, 1].
    """
    if total_votes == 0:
        return 0.0
    z = 1.9600  # 95% confidence z-score
    z2 = z * z   # 3.8416
    p_hat = upvotes / total_votes
    n = total_votes
    numerator = p_hat + z2 / (2 * n) - z * math.sqrt(
        (p_hat * (1 - p_hat) + z2 / (4 * n)) / n
    )
    return numerator / (1 + z2 / n)


async def apply_vote_to_trace(
    db: AsyncSession,
    trace_id: uuid.UUID,
    vote_weight: float,
    is_upvote: bool,
) -> None:
    """Atomically apply a vote to a trace and promote if threshold is reached.

    Increments confirmation_count by 1 and adjusts trust_score by
    +vote_weight (upvote) or -vote_weight (downvote) using a single atomic
    UPDATE statement — no SELECT is performed before the UPDATE.

    After the UPDATE, the trace is re-queried to check promotion eligibility.
    If status is pending, confirmation_count >= validation_threshold, and
    trust_score > 0, the trace is promoted to 'validated'.

    Args:
        db: The async SQLAlchemy session (caller manages commit/rollback).
        trace_id: UUID of the trace receiving the vote.
        vote_weight: Positive float weight for this vote (typically 1.0).
        is_upvote: True for an upvote (+weight), False for a downvote (-weight).
    """
    score_delta = vote_weight if is_upvote else -vote_weight

    # Atomic UPDATE — column expressions prevent read-modify-write races
    await db.execute(
        update(Trace)
        .where(Trace.id == trace_id)
        .values(
            confirmation_count=Trace.confirmation_count + 1,
            trust_score=Trace.trust_score + score_delta,
        )
        .execution_options(synchronize_session=False)
    )

    # Re-query to check promotion eligibility
    result = await db.execute(
        select(Trace.status, Trace.confirmation_count, Trace.trust_score).where(
            Trace.id == trace_id
        )
    )
    row = result.one_or_none()
    if row is None:
        return

    status, confirmation_count, trust_score = row

    # Promote if pending, threshold reached, and net positive trust
    if (
        status == TraceStatus.pending
        and confirmation_count >= settings.validation_threshold
        and trust_score > 0
    ):
        await db.execute(
            update(Trace)
            .where(Trace.id == trace_id)
            .values(status=TraceStatus.validated)
            .execution_options(synchronize_session=False)
        )


# Minimum weight for new contributors — creates measurable difference vs established
# contributors per REPU-01 success criterion. An established contributor with
# wilson_score=0.8 has 8x the vote influence of a new contributor.
BASE_WEIGHT = 0.1


async def get_vote_weight_for_trace(
    db: AsyncSession,
    voter_id: uuid.UUID,
    trace_tags: list[str],
) -> float:
    """Get the voter's effective weight for a trace based on domain reputation.

    Finds all domain reputation rows for this voter matching any of the trace's
    tags. Returns the maximum Wilson score across matching domains, or BASE_WEIGHT
    if no domain match exists.

    When trace has no tags, falls back to users.reputation_score (the global
    Wilson score). This is correct — untagged traces are domain-agnostic.

    Args:
        db: Async SQLAlchemy session.
        voter_id: UUID of the user casting the vote.
        trace_tags: List of normalized tag name strings from the trace.

    Returns:
        Vote weight as a float >= BASE_WEIGHT.
    """
    if not trace_tags:
        result = await db.execute(
            select(User.reputation_score).where(User.id == voter_id)
        )
        overall = result.scalar_one_or_none() or BASE_WEIGHT
        return max(BASE_WEIGHT, overall)

    result = await db.execute(
        select(ContributorDomainReputation.wilson_score)
        .where(ContributorDomainReputation.contributor_id == voter_id)
        .where(ContributorDomainReputation.domain_tag.in_(trace_tags))
    )
    domain_scores = [row[0] for row in result.fetchall()]

    if not domain_scores:
        return BASE_WEIGHT
    return max(BASE_WEIGHT, max(domain_scores))


async def update_contributor_domain_reputation(
    db: AsyncSession,
    contributor_id: uuid.UUID,
    domain_tags: list[str],
    is_upvote: bool,
) -> None:
    """Atomically update per-domain reputation for a trace contributor.

    For each domain tag on the voted trace, upserts a
    contributor_domain_reputation row incrementing the appropriate counter,
    then recomputes and stores the Wilson score.

    Also updates users.reputation_score with the aggregate Wilson score
    across all domains.

    Args:
        db: Async SQLAlchemy session (caller manages commit).
        contributor_id: UUID of the trace author receiving the reputation effect.
        domain_tags: Normalized tag names from the voted trace.
        is_upvote: True for upvote, False for downvote.
    """
    if not domain_tags:
        return

    for tag in domain_tags:
        up_delta = 1 if is_upvote else 0
        down_delta = 0 if is_upvote else 1

        stmt = pg_insert(ContributorDomainReputation).values(
            contributor_id=contributor_id,
            domain_tag=tag,
            upvote_count=up_delta,
            downvote_count=down_delta,
            wilson_score=0.0,
        ).on_conflict_do_update(
            constraint=CDR_UNIQUE_CONSTRAINT,
            set_={
                "upvote_count": ContributorDomainReputation.upvote_count + up_delta,
                "downvote_count": ContributorDomainReputation.downvote_count + down_delta,
            }
        ).returning(
            ContributorDomainReputation.upvote_count,
            ContributorDomainReputation.downvote_count,
            ContributorDomainReputation.id,
        )

        result = await db.execute(stmt)
        row = result.one()
        new_wilson = wilson_score_lower_bound(
            row.upvote_count, row.upvote_count + row.downvote_count
        )

        await db.execute(
            update(ContributorDomainReputation)
            .where(ContributorDomainReputation.id == row.id)
            .values(wilson_score=new_wilson)
            .execution_options(synchronize_session=False)
        )

    # Recompute aggregate Wilson score on users.reputation_score
    agg_result = await db.execute(
        select(
            func.sum(ContributorDomainReputation.upvote_count),
            func.sum(ContributorDomainReputation.downvote_count),
        ).where(ContributorDomainReputation.contributor_id == contributor_id)
    )
    agg_row = agg_result.one()
    total_up = agg_row[0] or 0
    total_down = agg_row[1] or 0
    overall_wilson = wilson_score_lower_bound(total_up, total_up + total_down)

    await db.execute(
        update(User)
        .where(User.id == contributor_id)
        .values(reputation_score=overall_wilson)
        .execution_options(synchronize_session=False)
    )
