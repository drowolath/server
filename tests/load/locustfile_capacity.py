"""Locust load test: HNSW p99 latency validation at 100K trace scale.

Exercises POST /api/v1/traces/search with diverse realistic queries to measure
end-to-end search latency. Target: p99 < 50ms for HNSW ANN portion.

NOTE: The search endpoint latency includes the OpenAI embedding API call for the
query vector. The p99 target of 50ms is for the HNSW ANN portion. If p99 exceeds
50ms, check whether the bottleneck is embedding API or HNSW by comparing against
raw SQL EXPLAIN ANALYZE times from psql.

Run command:
    # IMPORTANT: Set high rate limit for capacity testing — default 60/min causes
    # 429s within 6 seconds per user (10 RPS * 6s = 60 requests = bucket exhausted).
    RATE_LIMIT_READ_PER_MINUTE=10000 locust -f tests/load/locustfile_capacity.py \\
      --host http://localhost:8000 \\
      --users 20 --spawn-rate 5 --run-time 60s \\
      --headless --only-summary --csv=results/capacity

    # Check p99:
    # awk -F',' 'NR==2{print "p99:", $12, "ms"}' results/capacity_stats.csv
    # Success criterion: p99 < 50ms

Prerequisites:
    1. Start stack: docker compose -f docker-compose.yml -f docker-compose.capacity.yml up
    2. Populate 100K traces: python api/scripts/generate_capacity_data.py
    3. mkdir -p results/
"""

from locust import HttpUser, task, constant

SEARCH_QUERIES = [
    "react hooks useState",
    "postgresql migration alembic",
    "docker compose healthcheck",
    "fastapi async sqlalchemy",
    "python error handling retry",
    "github actions ci pipeline",
    "jwt authentication middleware",
    "redis caching ttl pattern",
    "typescript generics utility types",
    "pytest fixtures conftest setup",
]


class SearchLoadUser(HttpUser):
    """Simulates an agent performing rapid search queries at 10 RPS."""

    wait_time = constant(0.1)  # 10 RPS per user

    def on_start(self) -> None:
        """Register a test user and retrieve API key before starting load."""
        resp = self.client.post(
            "/api/v1/keys",
            json={"email": f"load-{id(self)}@test.invalid"},
        )
        if resp.status_code == 201:
            key_data = resp.json()
            self.headers = {"X-API-Key": key_data["api_key"]}
        else:
            # If registration fails (e.g. concurrent duplicate), use a fallback
            self.headers = {}

        self._query_idx = 0

    @task
    def search(self) -> None:
        """Execute a search query against the HNSW-indexed traces."""
        query = SEARCH_QUERIES[self._query_idx % len(SEARCH_QUERIES)]
        self._query_idx += 1
        self.client.post(
            "/api/v1/traces/search",
            json={"q": query, "limit": 10},
            headers=self.headers,
            name="/api/v1/traces/search",
        )
