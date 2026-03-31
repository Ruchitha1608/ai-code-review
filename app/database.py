"""
Database connection and session management using SQLAlchemy async with asyncpg.
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/code_review",
)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create all tables defined in models."""
    from app.models import Base as ModelsBase  # noqa: F401 — import triggers registration

    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)


async def check_db_health() -> bool:
    """Return True if the database is reachable."""
    from sqlalchemy import text

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Synchronous session for Celery tasks (uses psycopg2) — lazily initialized
# ---------------------------------------------------------------------------
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

_sync_engine = None
_SyncSessionLocal = None


def _get_sync_session_factory():
    global _sync_engine, _SyncSessionLocal
    if _SyncSessionLocal is None:
        _sync_engine = create_engine(
            SYNC_DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        _SyncSessionLocal = sessionmaker(
            bind=_sync_engine,
            autoflush=False,
            autocommit=False,
        )
    return _SyncSessionLocal


def get_sync_db() -> Session:
    """Return a synchronous database session for Celery tasks."""
    return _get_sync_session_factory()()
