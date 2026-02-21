"""Hybrid semantic + tag search endpoint.

POST /api/v1/traces/search -- search traces by natural language query, tags, or both.

Search modes:
  - Semantic-only (q provided, tags empty): cosine ANN over pgvector embeddings, trust re-ranked
  - Tag-only (q omitted, tags provided): SQL filter ordered by trust_score DESC, no embed call
  - Hybrid (q + tags): cosine ANN with tag pre-filter, trust re-ranked
  - Both empty: 422 validation error
"""

import math
import time
import structlog
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from prometheus_client import Counter, Histogram
from app.dependencies import CurrentUser, DbSession
from app.middleware.rate_limiter import ReadRateLimit
from app.schemas.search import TraceSearchRequest, TraceSearchResult, TraceSearchResponse
from app.models.trace import Trace
from app.models.tag import Tag, trace_tags
from app.services.embedding import EmbeddingService, EmbeddingSkippedError
from app.services.tags import normalize_tag

log = structlog.get_logger()
_embedding_svc = EmbeddingService()

# Search metrics (defined here; 03-03 may consolidate into app.metrics)
search_requests = Counter(
    "commontrace_search_requests_total",
    "Total search requests",
    ["has_tags"],
)
search_duration = Histogram(
    "commontrace_search_duration_seconds",
    "End-to-end search latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)

router = APIRouter(prefix="/api/v1", tags=["search"])

# Over-fetch from ANN before re-ranking to ensure we have enough candidates
SEARCH_LIMIT_ANN = 100


@router.post("/traces/search", response_model=TraceSearchResponse)
async def search_traces(
    body: TraceSearchRequest,
    user: CurrentUser,
    db: DbSession,
    _rate: ReadRateLimit,
) -> TraceSearchResponse:
    """Search traces by natural language query, tags, or both.

    Search modes:
    - q only: cosine ANN over pgvector embeddings, trust-weighted re-ranking
    - tags only: SQL tag filter ordered by trust_score DESC (no embedding service call)
    - q + tags: cosine ANN with tag pre-filter, trust-weighted re-ranking
    - neither: 422 validation error

    Flagged traces are always excluded. Traces with embedding IS NULL are excluded
    only when q is provided (semantic ranking requires an embedding).
    """
    start = time.monotonic()
    search_requests.labels(has_tags=str(bool(body.tags)).lower()).inc()

    # Step A: Embed the query text (only when q is provided)
    query_vector: Optional[list[float]] = None
    if body.q is not None:
        try:
            query_vector, _, _ = await _embedding_svc.embed(body.q)
        except EmbeddingSkippedError:
            raise HTTPException(
                status_code=503,
                detail="Search unavailable — embedding service not configured (OPENAI_API_KEY required)",
            )
    else:
        # Tag-only mode: validate that at least tags are provided
        if not body.tags:
            raise HTTPException(
                status_code=422,
                detail="At least one of 'q' or 'tags' must be provided",
            )

    # Step B: Set HNSW search parameters (only when using vector search)
    if query_vector is not None:
        await db.execute(text("SET LOCAL hnsw.ef_search = 64"))

    # Normalize tags for consistent matching
    normalized_tags = [normalize_tag(t) for t in body.tags]

    results: list[TraceSearchResult] = []

    if query_vector is not None:
        # Step C Path 1: Semantic search (q is provided, query_vector exists)
        distance_col = Trace.embedding.cosine_distance(query_vector).label("distance")

        stmt = (
            select(Trace, distance_col)
            .where(Trace.embedding.is_not(None))
            .where(Trace.embedding_model_id == "text-embedding-3-small")
            .where(Trace.is_flagged.is_(False))
            .options(selectinload(Trace.tags))
            .order_by(distance_col)
            .limit(SEARCH_LIMIT_ANN)
        )

        # Step D: Tag pre-filter (if tags provided) — Path 1
        if normalized_tags:
            stmt = (
                stmt
                .join(trace_tags, trace_tags.c.trace_id == Trace.id)
                .join(Tag, Tag.id == trace_tags.c.tag_id)
                .where(Tag.name.in_(normalized_tags))
                .group_by(Trace.id, Trace.embedding.cosine_distance(query_vector))
                .having(func.count(func.distinct(Tag.id)) == len(normalized_tags))
            )

        # Step E: Execute and re-rank
        result = await db.execute(stmt)
        rows = result.all()  # list of Row(Trace, distance)

        # Trust-weighted re-ranking
        ranked = sorted(
            rows,
            key=lambda r: (1.0 - r.distance) * math.log1p(max(0.0, r.Trace.trust_score) + 1),
            reverse=True,
        )[:body.limit]

        # Step F: Serialize response — Path 1 (semantic)
        for row in ranked:
            similarity = 1.0 - row.distance
            combined = similarity * math.log1p(max(0.0, row.Trace.trust_score) + 1)
            tag_names = [tag.name for tag in row.Trace.tags]
            results.append(
                TraceSearchResult(
                    id=row.Trace.id,
                    title=row.Trace.title,
                    context_text=row.Trace.context_text,
                    solution_text=row.Trace.solution_text,
                    trust_score=row.Trace.trust_score,
                    status=row.Trace.status,
                    tags=tag_names,
                    similarity_score=similarity,
                    combined_score=combined,
                    contributor_id=row.Trace.contributor_id,
                    created_at=row.Trace.created_at,
                )
            )

    else:
        # Step C Path 2: Tag-only search (q is None)
        # Note: does NOT filter out embedding IS NULL traces — valid results for tag-only
        stmt = (
            select(Trace)
            .where(Trace.is_flagged.is_(False))
            .options(selectinload(Trace.tags))
            .order_by(Trace.trust_score.desc())
            .limit(body.limit)
        )

        # Step D: Tag pre-filter (if tags provided) — Path 2
        if normalized_tags:
            stmt = (
                stmt
                .join(trace_tags, trace_tags.c.trace_id == Trace.id)
                .join(Tag, Tag.id == trace_tags.c.tag_id)
                .where(Tag.name.in_(normalized_tags))
                .group_by(Trace.id)
                .having(func.count(func.distinct(Tag.id)) == len(normalized_tags))
            )

        # Step E: Execute — Path 2 (already ordered by trust_score DESC, no re-ranking needed)
        result = await db.execute(stmt)
        rows_tag_only = result.scalars().all()  # list of Trace

        # Step F: Serialize response — Path 2 (tag-only)
        for trace in rows_tag_only:
            similarity = 0.0  # No semantic similarity in tag-only mode
            combined = float(trace.trust_score)
            tag_names = [tag.name for tag in trace.tags]
            results.append(
                TraceSearchResult(
                    id=trace.id,
                    title=trace.title,
                    context_text=trace.context_text,
                    solution_text=trace.solution_text,
                    trust_score=trace.trust_score,
                    status=trace.status,
                    tags=tag_names,
                    similarity_score=similarity,
                    combined_score=combined,
                    contributor_id=trace.contributor_id,
                    created_at=trace.created_at,
                )
            )

    # Step G: Search metrics instrumentation
    search_duration.observe(time.monotonic() - start)
    log.info(
        "search_executed",
        query_len=len(body.q) if body.q else 0,
        tag_count=len(body.tags),
        result_count=len(results),
    )

    return TraceSearchResponse(results=results, total=len(results), query=body.q)
