from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

# Embedding worker metrics
embeddings_processed = Counter(
    "commontrace_embeddings_processed_total",
    "Total embeddings generated",
    ["model", "status"],  # status: success | error | skipped
)

embedding_duration = Histogram(
    "commontrace_embedding_duration_seconds",
    "Time to generate one embedding",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# NOTE: Search endpoint metrics (search_requests, search_duration) are defined
# directly in api/app/routers/search.py by Plan 03-02. Do NOT duplicate them here
# to avoid prometheus_client duplicate registration errors.

# HTTP request metrics (from middleware)
http_requests = Counter(
    "commontrace_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration = Histogram(
    "commontrace_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


async def metrics_endpoint():
    """FastAPI endpoint handler that returns Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
