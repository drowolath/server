"""Import seed traces into the database.

Loads traces from api/fixtures/seed_traces.json (or a custom path) and inserts
them into the database as pre-validated seed traces.

Key behaviors:
- Creates a dedicated seed contributor user (seeds@commontrace.internal) if not present
- Idempotent per trace: checks title + is_seed before inserting (skips duplicates)
- Traces are inserted with status=validated, is_seed=True, trust_score=1.0
- Embeddings are left NULL — the Phase 3 embedding worker picks them up automatically
- Tags are normalized and validated before insertion

Usage:
    # From project root:
    cd api
    DATABASE_URL="postgresql+asyncpg://..." uv run python -m scripts.import_seeds

    # With custom fixtures path:
    uv run python -m scripts.import_seeds --fixtures-path api/fixtures/seed_traces.json

    # With DATABASE_URL from .env (pydantic-settings loads it automatically):
    uv run python -m scripts.import_seeds
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Support running from both project root and api/ directory
_api_root = Path(__file__).parent.parent  # api/
if str(_api_root) not in sys.path:
    sys.path.insert(0, str(_api_root))

from app.config import settings
from app.models.tag import Tag, trace_tags
from app.models.trace import Trace, TraceStatus
from app.models.user import User
from app.services.tags import normalize_tag, validate_tag

SEED_USER_EMAIL = "seeds@commontrace.internal"
SEED_USER_DISPLAY_NAME = "CommonTrace Seeds"

DEFAULT_FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "seed_traces.json"


async def get_or_create_seed_user(session: AsyncSession) -> User:
    """Get the seed contributor user, creating it if it does not exist.

    The seed user email (seeds@commontrace.internal) is the idempotency key.
    Returns the User ORM object with its ID populated.
    """
    result = await session.execute(
        select(User).where(User.email == SEED_USER_EMAIL)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=SEED_USER_EMAIL,
            display_name=SEED_USER_DISPLAY_NAME,
            is_seed=True,
        )
        session.add(user)
        await session.flush()  # Populate user.id without committing

    return user


async def get_or_create_tag(session: AsyncSession, raw_name: str) -> Tag | None:
    """Normalize and validate a tag name, then get or create the Tag row.

    Returns the Tag ORM object, or None if the normalized tag is invalid.
    """
    normalized = normalize_tag(raw_name)
    if not validate_tag(normalized):
        return None

    result = await session.execute(select(Tag).where(Tag.name == normalized))
    tag = result.scalar_one_or_none()

    if tag is None:
        tag = Tag(name=normalized)
        session.add(tag)
        await session.flush()  # Populate tag.id

    return tag


async def import_seeds(fixtures_path: Path) -> None:
    """Import seed traces from the given JSON file into the database.

    This function is the main entry point. It:
    1. Creates a database engine from settings.database_url
    2. Gets or creates the seed contributor user
    3. Iterates over each trace in the fixture file
    4. Skips traces that already exist (idempotency: title + is_seed match)
    5. Inserts new traces with pre-validated status and NULL embedding
    6. Processes tags via normalize_tag + validate_tag + get-or-create
    7. Commits all changes in a single transaction
    8. Prints a summary: "Seed import complete: N inserted, M skipped"
    """
    if not fixtures_path.exists():
        print(f"Error: fixtures file not found: {fixtures_path}", file=sys.stderr)
        sys.exit(1)

    with open(fixtures_path, "r") as fh:
        fixture_data = json.load(fh)

    print(f"Loaded {len(fixture_data)} traces from {fixtures_path}")

    # Build a standalone engine using settings — not the app's shared engine,
    # so this script can run independently without starting the full app.
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    inserted = 0
    skipped = 0

    async with session_factory() as session:
        seed_user = await get_or_create_seed_user(session)

        for trace_json in fixture_data:
            title = trace_json["title"]

            # Idempotency check: skip if a seed trace with this exact title exists
            result = await session.execute(
                select(Trace).where(Trace.title == title, Trace.is_seed.is_(True))
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                skipped += 1
                continue

            # Create the trace — embedding left NULL so the Phase 3 worker picks it up
            trace = Trace(
                title=title,
                context_text=trace_json["context"],    # JSON: "context" -> ORM: "context_text"
                solution_text=trace_json["solution"],  # JSON: "solution" -> ORM: "solution_text"
                status=TraceStatus.validated,          # Pre-validated — bypasses confirmation flow
                is_seed=True,
                trust_score=1.0,
                confirmation_count=2,                  # >= validation_threshold default (2)
                contributor_id=seed_user.id,
                agent_model=trace_json.get("agent_model"),
                agent_version=trace_json.get("agent_version"),
                embedding=None,                        # Left NULL; embedding worker processes these
            )
            session.add(trace)
            await session.flush()  # Populate trace.id for join table insertion

            # Process tags: normalize -> validate -> get-or-create -> insert into join table
            for raw_tag in trace_json.get("tags", []):
                tag = await get_or_create_tag(session, raw_tag)
                if tag is None:
                    continue  # Skip invalid tags silently
                # Direct insert into trace_tags join table (not relationship .append())
                # — codebase convention per 01-03 decision: direct insert in async context
                await session.execute(
                    insert(trace_tags).values(trace_id=trace.id, tag_id=tag.id)
                )

            inserted += 1

        await session.commit()

    await engine.dispose()

    print(f"Seed import complete: {inserted} inserted, {skipped} skipped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import seed traces into the CommonTrace database"
    )
    parser.add_argument(
        "--fixtures-path",
        type=Path,
        default=DEFAULT_FIXTURES_PATH,
        help=f"Path to the seed traces JSON file (default: {DEFAULT_FIXTURES_PATH})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(import_seeds(args.fixtures_path))
