import hashlib
import hmac
import json
import os
from urllib.parse import urlencode

os.environ["BOT_TOKEN"] = "123456789:TESTTOKEN"
os.environ["GOFILE_API_TOKEN"] = "test-gofile-token"
os.environ["GOFILE_ACCOUNT_ID"] = "acc-test"
os.environ["ADMIN_TELEGRAM_ID"] = "4242"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./pytest-unused.db"
os.environ["WEBAPP_URL"] = "http://localhost:8000"
os.environ["PAYMENT_CARD_NUMBER"] = "8600 0000 0000 0000"
os.environ["PAYMENT_CARD_NAME"] = "TEST USER"
os.environ["GOFILE_MAX_STORAGE_GB"] = "100"
os.environ["GOFILE_MAX_FILE_SIZE_GB"] = "10"
os.environ["GOFILE_STORAGE_WARNING_PERCENT"] = "80"
os.environ["GOFILE_STORAGE_BLOCK_PERCENT"] = "95"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.api.deps import get_storage_dep
from backend.database.database import configure_sqlite, get_session
from backend.database.models import Base
from backend.main import app
from backend.utils.security import reset_rate_limits
from tests.fakes import FakeStorage

TOKEN = os.environ["BOT_TOKEN"]


def make_init_data(user: dict, start_param: str | None = None, auth_date: int | None = None, bot_token: str = TOKEN) -> str:
    import time

    payload = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAE",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    if start_param:
        payload["start_param"] = start_param
    check = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(payload)


def auth_headers(telegram_id: int, first_name: str = "Ali", username: str = "ali", start_param: str | None = None) -> dict:
    user = {"id": telegram_id, "first_name": first_name, "username": username}
    return {"X-Telegram-Init-Data": make_init_data(user, start_param=start_param)}


@pytest.fixture
async def database():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    configure_sqlite(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


@pytest.fixture
async def api():
    reset_rate_limits()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    configure_sqlite(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    storage = FakeStorage()

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_storage_dep] = lambda: storage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, storage, factory
    app.dependency_overrides.clear()
    await engine.dispose()
