"""
VisionX Database Session Management
Async SQLAlchemy engine and session factory with proper connection pooling.
Connects to PostgreSQL (AWS RDS or local) via DATABASE_URL.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import settings
from backend.core.exceptions import DatabaseError, ConfigurationError


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _build_connection_string() -> str:
    """
    Build an async PostgreSQL connection string from settings.
    
    Uses DATABASE_URL.
    """
    if settings.DATABASE_URL:
        # Convert sync URL to async if needed
        url = settings.DATABASE_URL
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    raise ConfigurationError(
        message="Database not configured. Set DATABASE_URL in backend/.env."
    )


def get_engine() -> AsyncEngine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        connection_string = _build_connection_string()
        _engine = create_async_engine(
            connection_string,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            echo=settings.DATABASE_ECHO,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.
    Automatically handles commit/rollback.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise DatabaseError(message=str(e)) from e
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize the database: create all tables.
    Should be called during application startup.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the database engine. Should be called during shutdown."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


async def check_db_connection() -> bool:
    """Check if the database connection is healthy."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
