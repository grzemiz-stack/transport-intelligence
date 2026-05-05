"""Asynchroniczne polaczenie z PostgreSQL przez SQLAlchemy async engine.

Connection pool: pool_size=20, max_overflow=10.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Zwraca sesje bazy danych jako async context manager."""
    async with async_session() as session:
        yield session


async def dispose_engine() -> None:
    """Zamyka connection pool."""
    await engine.dispose()
