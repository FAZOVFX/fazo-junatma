"""Async engine and session helpers. PostgreSQL in production, SQLite locally."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def to_async_url(url: str) -> str:
    raw = (url or "").strip()
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    if raw.startswith("postgresql://") and "+asyncpg" not in raw.split("://", 1)[0]:
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    if raw.startswith("sqlite://") and "+aiosqlite" not in raw.split("://", 1)[0]:
        raw = "sqlite+aiosqlite://" + raw[len("sqlite://") :]
    if raw.startswith("postgresql+asyncpg://") and "sslmode=" in raw:
        raw = raw.replace("sslmode=", "ssl=")
    return raw


def configure_sqlite(engine: AsyncEngine) -> None:
    if not engine.url.drivername.startswith("sqlite"):
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = to_async_url(get_settings().database_url)
        kwargs: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs = {"connect_args": {"check_same_thread": False}}
        _engine = create_async_engine(url, **kwargs)
        configure_sqlite(_engine)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    maker = get_sessionmaker()
    session = maker()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
