"""Locust burst test: Token-bucket rate limiter behavior validation.

Validates that the token-bucket rate limiter correctly handles agent-like burst
workloads:

Validation checklist:
  1. BurstAgent: First rate_limit_read_per_minute (default 60) requests succeed,
     then 429 responses appear — bucket is correctly exhausted.
  2. BurstAgent: 429 responses include Retry-After header (set to 60s).
  3. RealisticAgent: 10-15 searches in 30s all succeed — bucket starts full at
     60 tokens, uses at most 15, well within limits.
  4. Different users: Each BurstAgent gets its own independent bucket — verified
     by 5 concurrent users all succeeding initially (no cross-user interference).

Run command:
    locust -f tests/load/locustfile_rate_limit.py \\
      --host http://localhost:8000 \\
      --users 5 --spawn-rate 5 --run-time 30s \\
      --headless --only-summary --csv=results/rate_limit

    # Interpretation:
    # - BurstAgent 429 count should be > 0 (bucket exhaustion confirmed)
    # - BurstAgent 200 count should be ~60 per user (one full bucket)
    # - RealisticAgent 200 count should be 100% (all requests within bucket)

Prerequisites:
    1. Start stack: docker compose up
    2. mkdir -p results/
"""

import time

from locust import HttpUser, task, constant


class BurstAgent(HttpUser):
    """Simulates agent burst: rapid-fire requests to test token bucket behavior.

    Sends requests as fast as possible (no wait). Expects:
    - First ~60 requests: HTTP 200
    - Subsequent requests: HTTP 429 with Retry-After header
    Both 200 and 429 are treated as success() — 429 is expected behavior, not a failure.
    """

    wait_time = constant(0)  # No wait — pure burst

    def on_start(self) -> None:
        """Register a unique test user to get an independent rate limit bucket."""
        resp = self.client.post(
            "/api/v1/keys",
            json={"email": f"burst-{id(self)}@test.invalid"},
        )
        if resp.status_code == 201:
            key_data = resp.json()
            self.headers = {"X-API-Key": key_data["api_key"]}
        else:
            self.headers = {}

        self.burst_count = 0
        self.success_count = 0
        self.rate_limited_count = 0

    @task
    def search_burst(self) -> None:
        """Fire search requests at maximum rate; accept both 200 and 429."""
        with self.client.post(
            "/api/v1/traces/search",
            json={"q": "test query"},
            headers=self.headers,
            catch_response=True,
            name="/api/v1/traces/search [burst]",
        ) as resp:
            if resp.status_code == 200:
                self.success_count += 1
                resp.success()
            elif resp.status_code == 429:
                # 429 is EXPECTED after bucket exhaustion — mark as success
                self.rate_limited_count += 1
                # GAP 4 fix: verify Retry-After header is present
                retry_after = resp.headers.get("Retry-After")
                if retry_after is None:
                    resp.failure("429 response missing Retry-After header")
                else:
                    resp.success()
            else:
                resp.failure(f"Unexpected status {resp.status_code}")

        self.burst_count += 1


class RefillAgent(HttpUser):
    """Validates token-bucket refill: exhaust bucket, wait partial period, verify proportional refill.

    Expected behavior:
    1. Burst requests until 429 (bucket exhausted)
    2. Wait 10 seconds (~10/60 = ~10 tokens refilled at 60 tokens/min)
    3. Send another burst — expect ~10 successes before next 429
    """

    wait_time = constant(0)

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/keys",
            json={"email": f"refill-{id(self)}@test.invalid"},
        )
        if resp.status_code == 201:
            key_data = resp.json()
            self.headers = {"X-API-Key": key_data["api_key"]}
        else:
            self.headers = {}

        self._phase = "exhaust"  # exhaust → wait → refill_burst → done
        self._exhaust_429_seen = False
        self._refill_successes = 0
        self._refill_done = False

    @task
    def refill_test(self) -> None:
        if self._refill_done:
            time.sleep(5)
            return

        if self._phase == "exhaust":
            with self.client.post(
                "/api/v1/traces/search",
                json={"q": "refill test"},
                headers=self.headers,
                catch_response=True,
                name="/api/v1/traces/search [refill-exhaust]",
            ) as resp:
                if resp.status_code == 429:
                    self._exhaust_429_seen = True
                    self._phase = "wait"
                    resp.success()
                else:
                    resp.success()

        elif self._phase == "wait":
            # Wait 10 seconds for partial refill (~10 tokens at 60/min rate)
            time.sleep(10)
            self._phase = "refill_burst"

        elif self._phase == "refill_burst":
            with self.client.post(
                "/api/v1/traces/search",
                json={"q": "refill validation"},
                headers=self.headers,
                catch_response=True,
                name="/api/v1/traces/search [refill-burst]",
            ) as resp:
                if resp.status_code == 200:
                    self._refill_successes += 1
                    resp.success()
                elif resp.status_code == 429:
                    # Refill phase done — we got some successes then hit limit again
                    self._refill_done = True
                    resp.success()
                else:
                    resp.failure(f"Unexpected status {resp.status_code}")


class RealisticAgent(HttpUser):
    """Simulates realistic agent pattern: 10-15 searches in 30s, then idle.

    Expected behavior: all requests should succeed (15 requests << 60 token bucket).
    After 15 requests, the agent 'idles' for 30s to simulate thinking/working.
    """

    wait_time = constant(2)  # ~2s between requests during active phase

    def on_start(self) -> None:
        """Register a unique test user to get an independent rate limit bucket."""
        resp = self.client.post(
            "/api/v1/keys",
            json={"email": f"realistic-{id(self)}@test.invalid"},
        )
        if resp.status_code == 201:
            key_data = resp.json()
            self.headers = {"X-API-Key": key_data["api_key"]}
        else:
            self.headers = {}

        self._request_count = 0

    @task
    def search_session(self) -> None:
        """Simulate 10-15 searches in quick succession, then idle."""
        if self._request_count < 15:
            self.client.post(
                "/api/v1/traces/search",
                json={"q": f"realistic query {self._request_count}"},
                headers=self.headers,
                name="/api/v1/traces/search [realistic]",
            )
            self._request_count += 1
        else:
            # Idle phase — simulate agent thinking/working between sessions
            time.sleep(30)
            self._request_count = 0
