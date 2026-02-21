"""Seed fixture data into the database.

Loads sample traces from sample_traces.json and inserts them into the database.
Seed traces are auto-validated (status=validated, is_seed=True) per user decision.

Usage:
    cd api
    DATABASE_URL="postgresql+asyncpg://..." uv run python -m fixtures.seed_fixtures

The script is idempotent — running it multiple times is safe. If a seed user
already exists, the script prints "Already seeded" and exits.
"""
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_factory
from app.models.tag import Tag, trace_tags
from app.models.trace import Trace, TraceStatus
from app.models.user import User
from app.services.tags import normalize_tag

# Path to the sample traces JSON file (relative to this file)
FIXTURES_DIR = Path(__file__).parent
SAMPLE_TRACES_FILE = FIXTURES_DIR / "sample_traces.json"

SEED_USER_EMAIL = "seed@commontrace.dev"


async def get_or_create_tag(session, name: str) -> Tag:
    """Get an existing tag by normalized name, or create it if not found."""
    normalized_name = normalize_tag(name)

    # Try to find existing tag
    result = await session.execute(select(Tag).where(Tag.name == normalized_name))
    tag = result.scalar_one_or_none()

    if tag is None:
        tag = Tag(name=normalized_name)
        session.add(tag)
        # Flush to get the ID but don't commit yet
        await session.flush()

    return tag


async def seed() -> None:
    """Load fixture data into the database.

    Creates a seed user and 12 sample traces with realistic content.
    All seed traces are set to status=validated and is_seed=True.
    Tags are normalized via normalize_tag() before insertion.

    This function is idempotent — safe to run multiple times.
    """
    async with async_session_factory() as session:
        # Check if already seeded (idempotency check)
        result = await session.execute(
            select(User).where(User.email == SEED_USER_EMAIL)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user is not None:
            print("Already seeded — seed user already exists, skipping.")
            return

        # Load fixture data
        if not SAMPLE_TRACES_FILE.exists():
            print(f"Error: sample_traces.json not found at {SAMPLE_TRACES_FILE}", file=sys.stderr)
            sys.exit(1)

        with open(SAMPLE_TRACES_FILE, "r") as f:
            fixture_traces = json.load(f)

        print(f"Loading {len(fixture_traces)} sample traces...")

        # Create seed user
        seed_user = User(
            email=SEED_USER_EMAIL,
            display_name="CommonTrace Seed",
            is_seed=True,
        )
        session.add(seed_user)
        # Flush to get the seed user ID
        await session.flush()

        trace_count = 0
        tag_names_created: set[str] = set()

        for fixture in fixture_traces:
            # Create trace — seed traces are auto-validated
            trace = Trace(
                title=fixture["title"],
                context_text=fixture["context"],
                solution_text=fixture["solution"],
                status=TraceStatus.validated,
                is_seed=True,
                contributor_id=seed_user.id,
                agent_model=fixture.get("agent_model"),
                agent_version=fixture.get("agent_version"),
            )
            session.add(trace)
            # Flush to get trace ID before adding tags
            await session.flush()

            # Add normalized tags via direct insert into join table
            # (avoids lazy-load on trace.tags which fails in async context)
            for raw_tag in fixture.get("tags", []):
                tag = await get_or_create_tag(session, raw_tag)
                await session.execute(
                    trace_tags.insert().values(trace_id=trace.id, tag_id=tag.id)
                )
                tag_names_created.add(tag.name)

            trace_count += 1

        # Commit all changes in one transaction
        await session.commit()

        print(f"Seeding complete!")
        print(f"  Created: 1 seed user ({SEED_USER_EMAIL})")
        print(f"  Created: {trace_count} traces (status=validated, is_seed=True)")
        print(f"  Created/reused: {len(tag_names_created)} unique tags")
        print(f"  Tags: {sorted(tag_names_created)}")


if __name__ == "__main__":
    asyncio.run(seed())
