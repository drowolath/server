"""Embedding worker: polls for unembedded traces and stores OpenAI vectors.

Uses FOR UPDATE SKIP LOCKED to safely claim batches, allowing multiple worker
instances to run without double-processing the same trace.
"""
import asyncio
import time

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.logging_config import configure_logging
from app.metrics import embeddings_processed, embedding_duration
from app.models.trace import Trace
from app.services.embedding import EmbeddingService, EmbeddingSkippedError, OPENAI_MODEL

log = structlog.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 10


async def process_batch(db: AsyncSession, svc: EmbeddingService) -> int:
    """Claim a batch of unembedded traces with SKIP LOCKED and embed them.

    Returns:
        Number of traces processed in this batch.
    """
    stmt = (
        select(Trace)
        .where(Trace.embedding.is_(None))
        .with_for_update(skip_locked=True)
        .limit(BATCH_SIZE)
    )
    result = await db.execute(stmt)
    traces = result.scalars().all()

    if not traces:
        return 0

    processed = 0
    for trace in traces:
        text = f"{trace.title}\n{trace.context_text}\n{trace.solution_text}"
        start = time.monotonic()
        try:
            vector, model_id, model_version = await svc.embed(text)
        except EmbeddingSkippedError:
            log.warning(
                "embedding_skipped_no_api_key",
                message="OPENAI_API_KEY not configured — skipping entire batch.",
            )
            embeddings_processed.labels(model="none", status="skipped").inc()
            return 0
        except Exception as exc:
            log.error(
                "embedding_error",
                trace_id=str(trace.id),
                error=str(exc),
            )
            embeddings_processed.labels(model=OPENAI_MODEL, status="error").inc()
            embedding_duration.labels(model=OPENAI_MODEL).observe(time.monotonic() - start)
            continue

        embeddings_processed.labels(model=model_id, status="success").inc()
        embedding_duration.labels(model=model_id).observe(time.monotonic() - start)

        update_stmt = (
            update(Trace)
            .where(Trace.id == trace.id)
            .values(
                embedding=vector,
                embedding_model_id=model_id,
                embedding_model_version=model_version,
            )
            .execution_options(synchronize_session=False)
        )
        await db.execute(update_stmt)
        log.info("embedding_stored", trace_id=str(trace.id), model=model_id)
        processed += 1

    await db.commit()
    return processed


async def run_worker() -> None:
    """Main polling loop: claims and embeds unembedded traces every POLL_INTERVAL_SECONDS."""
    configure_logging()
    svc = EmbeddingService()
    log.info("embedding_worker_started", poll_interval=POLL_INTERVAL_SECONDS, batch_size=BATCH_SIZE)

    # Drift detection: warn if existing traces used a different model
    async with async_session_factory() as db:
        from sqlalchemy import func, select as sa_select
        result = await db.execute(
            sa_select(Trace.embedding_model_id, func.count())
            .where(Trace.embedding_model_id.is_not(None))
            .group_by(Trace.embedding_model_id)
        )
        model_counts = result.all()
        for model_id, count in model_counts:
            if model_id != OPENAI_MODEL:
                log.warning(
                    "embedding_model_drift_detected",
                    existing_model=model_id,
                    current_model=OPENAI_MODEL,
                    trace_count=count,
                )

    while True:
        try:
            async with async_session_factory() as db:
                count = await process_batch(db, svc)
                if count > 0:
                    log.info("batch_processed", count=count)
        except Exception as exc:
            log.error("worker_loop_error", error=str(exc))

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_worker())
