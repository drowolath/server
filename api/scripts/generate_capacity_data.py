"""Populate 100K synthetic traces with pre-computed embeddings for capacity testing.

This script inserts 100K traces with 1536-dim normalized random vectors directly
into the database using asyncpg (not ORM) for bulk performance.

Design notes:
- Does NOT call OpenAI API — uses random normalized vectors (numpy).
  Random normalized vectors are sufficient for HNSW latency benchmarking
  (tests index traversal mechanics, not semantic quality). Avoids $1.20+ in costs.
- Uses asyncpg executemany for bulk insert in batches of 1000 rows.
- Creates a dedicated capacity test user: capacity-test@commontrace.internal
- All traces: is_seed=True, status='validated', trust_score=1.0,
  confirmation_count=2, embedding_model_id='text-embedding-3-small'
- Generates realistic-looking metadata using faker with seed=42 (deterministic).
- Uses numpy with seed=42 for reproducible random vectors.

Embedding generation algorithm (tiled vectors with noise):
  1. Generate 1000 base normalized random vectors (1536-dim)
  2. For each of the 100K traces: pick base_vectors[i % 1000],
     add small Gaussian noise (sigma=0.05), renormalize.
  This creates clusters of similar vectors — more realistic ANN search behavior
  than purely random vectors.

Usage:
    # From project root, with DATABASE_URL set or using defaults:
    python api/scripts/generate_capacity_data.py

    # Or via uv:
    cd api && uv run python scripts/generate_capacity_data.py
"""

import asyncio
import os
import sys
import uuid

import asyncpg
import numpy as np
from faker import Faker

TOTAL_TRACES = 100_000
BATCH_SIZE = 1000
NUM_BASE_VECTORS = 1000
EMBEDDING_DIM = 1536
NOISE_SIGMA = 0.05

CAPACITY_USER_EMAIL = "capacity-test@commontrace.internal"
CAPACITY_USER_NAME = "Capacity Test Bot"


def _strip_asyncpg_scheme(url: str) -> str:
    """Convert SQLAlchemy-style URL to asyncpg-compatible URL.

    Strips '+asyncpg' from 'postgresql+asyncpg://...' to get 'postgresql://...'
    """
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _generate_base_vectors(rng: np.random.Generator) -> np.ndarray:
    """Generate NUM_BASE_VECTORS normalized random vectors of EMBEDDING_DIM dimensions."""
    raw = rng.standard_normal((NUM_BASE_VECTORS, EMBEDDING_DIM))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    return raw / norms


def _make_embedding(base_vectors: np.ndarray, idx: int, rng: np.random.Generator) -> list[float]:
    """Generate a single embedding: tile base vector + Gaussian noise, renormalize."""
    base = base_vectors[idx % NUM_BASE_VECTORS]
    noise = rng.normal(0, NOISE_SIGMA, EMBEDDING_DIM)
    vec = base + noise
    norm = np.linalg.norm(vec)
    if norm < 1e-10:
        norm = 1.0
    vec = vec / norm
    return vec.tolist()


async def generate_capacity_data(database_url: str) -> None:
    """Insert 100K synthetic traces with embeddings into the database.

    Args:
        database_url: PostgreSQL connection URL (asyncpg or SQLAlchemy format).
    """
    pg_url = _strip_asyncpg_scheme(database_url)
    print(f"Connecting to database...")
    conn = await asyncpg.connect(pg_url)

    try:
        # 1. Create capacity test user (ON CONFLICT DO NOTHING)
        print(f"Creating capacity test user: {CAPACITY_USER_EMAIL}")
        user_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO users (id, email, display_name, api_key_hash, reputation_score)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (email) DO NOTHING
            """,
            user_id,
            CAPACITY_USER_EMAIL,
            CAPACITY_USER_NAME,
            "capacity-test-key-hash-placeholder",
            0.0,
        )

        # Retrieve the actual user_id (may differ if user already existed)
        row = await conn.fetchrow("SELECT id FROM users WHERE email = $1", CAPACITY_USER_EMAIL)
        actual_user_id = str(row["id"])
        print(f"Using user_id: {actual_user_id}")

        # 2. Generate base vectors (seeded for reproducibility)
        print(f"Generating {NUM_BASE_VECTORS} base vectors (seed=42)...")
        rng = np.random.default_rng(42)
        base_vectors = _generate_base_vectors(rng)

        # 3. Faker for realistic metadata
        fake = Faker()
        Faker.seed(42)

        # 4. Batch insert 100K traces
        print(f"Inserting {TOTAL_TRACES:,} traces in batches of {BATCH_SIZE}...")
        inserted = 0

        for batch_start in range(0, TOTAL_TRACES, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, TOTAL_TRACES)
            batch = []

            for i in range(batch_start, batch_end):
                trace_id = str(uuid.uuid4())
                title = fake.sentence(nb_words=6).rstrip(".")
                context_text = fake.paragraph(nb_sentences=3)
                solution_text = fake.paragraph(nb_sentences=4)
                embedding = _make_embedding(base_vectors, i, rng)
                # pgvector expects the vector as a string in '[a,b,c,...]' format
                embedding_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"

                batch.append((
                    trace_id,
                    actual_user_id,
                    title,
                    context_text,
                    solution_text,
                    "validated",       # status
                    True,              # is_seed
                    False,             # is_stale
                    False,             # is_flagged
                    1.0,               # trust_score
                    2,                 # confirmation_count
                    embedding_str,     # embedding (pgvector string)
                    "text-embedding-3-small",  # embedding_model_id
                ))

            await conn.executemany(
                """
                INSERT INTO traces (
                    id, contributor_id, title, context_text, solution_text,
                    status, is_seed, is_stale, is_flagged, trust_score,
                    confirmation_count, embedding, embedding_model_id
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9, $10,
                    $11, $12::vector, $13
                )
                """,
                batch,
            )

            inserted += batch_end - batch_start
            if inserted % 10_000 == 0 or inserted == TOTAL_TRACES:
                print(f"  Inserted {inserted:,} / {TOTAL_TRACES:,} traces ({100*inserted//TOTAL_TRACES}%)")

        # 5. REINDEX to rebuild HNSW index for optimal graph quality
        print("Running REINDEX on ix_traces_embedding_hnsw to optimize HNSW graph...")
        await conn.execute("REINDEX INDEX CONCURRENTLY ix_traces_embedding_hnsw")
        print("REINDEX complete.")

        print(f"\nDone! Inserted {TOTAL_TRACES:,} traces with embeddings.")
        print(f"Capacity test user: {CAPACITY_USER_EMAIL} (id: {actual_user_id})")

    finally:
        await conn.close()


if __name__ == "__main__":
    # Read DATABASE_URL from environment, fall back to app.config default
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        try:
            # Allow importing from api/ directory
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from app.config import settings
            database_url = settings.database_url
        except ImportError:
            database_url = "postgresql+asyncpg://commontrace:commontrace@localhost:5432/commontrace"

    asyncio.run(generate_capacity_data(database_url))
