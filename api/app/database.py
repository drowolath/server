from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import event
from pgvector.asyncpg import register_vector

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)


@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_connection, connection_record):
    """Register pgvector types with asyncpg connection pool."""
    dbapi_connection.run_async(register_vector)


async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db():
    """FastAPI dependency: yields AsyncSession per request."""
    async with async_session_factory() as session:
        yield session
