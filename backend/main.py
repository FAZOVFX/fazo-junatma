"""FAZO JUNATMA web process: API, Mini App, and Telegram bot."""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_storage_dep, require_admin
from backend.api.routes import api_router
from backend.bot import runtime
from backend.bot.setup import setup_dispatcher
from backend.config import get_settings, missing_runtime_settings
from backend.database.database import get_session, get_sessionmaker
from backend.database.models import User
from backend.services import file_service
from backend.services.errors import AppError
from backend.services.storage_service import StorageService
from backend.services.subscription_service import expire_due_users
from backend.utils.security import install_log_redaction, webhook_secret

logger = logging.getLogger("fazo")
ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


def _under_pytest() -> bool:
    return "pytest" in sys.modules


class UploadSizeLimitMiddleware:
    """Reject oversized uploads before the body is stored."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/api/files/upload" and scope.get("method") == "POST":
            headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
            raw_length = headers.get("content-length")
            settings = get_settings()
            max_bytes = int(settings.gofile_max_file_size_gb * (1024**3)) + (1024 * 1024)
            if raw_length is None:
                response = JSONResponse({"detail": "Fayl hajmi aniqlanmadi."}, status_code=411)
                await response(scope, receive, send)
                return
            try:
                length = int(raw_length)
            except ValueError:
                length = max_bytes + 1
            if length > max_bytes:
                response = JSONResponse(
                    {"detail": "Fayl hajmi ruxsat etilgan chegaradan katta."},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"referrer-policy", b"no-referrer"))
                headers.append(
                    (
                        b"content-security-policy",
                        b"frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
                    )
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


async def _expiration_loop() -> None:
    while True:
        try:
            maker = get_sessionmaker()
            async with maker() as session:
                removed = await file_service.expire_due_files(session, runtime_storage())
                expired_users = await expire_due_users(session)
                if removed or expired_users:
                    logger.info("expiration files=%s users=%s", removed, expired_users)
        except Exception:
            logger.exception("expiration loop failed")
        await asyncio.sleep(300)


def runtime_storage() -> StorageService:
    return get_storage_dep()


async def _start_bot() -> None:
    settings = get_settings()
    if not settings.bot_token or _under_pytest():
        return
    runtime.bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    runtime.dp = setup_dispatcher()
    try:
        me = await runtime.bot.get_me()
        runtime.bot_username = me.username or ""
        logger.info("bot username=%s", runtime.bot_username)
        if settings.webapp_url.startswith("https://"):
            await runtime.bot.set_webhook(
                url=f"{settings.webapp_url.rstrip('/')}/telegram/webhook",
                secret_token=webhook_secret(settings.bot_token),
                allowed_updates=["message", "callback_query"],
            )
            logger.info("telegram webhook set")
        else:
            await runtime.bot.delete_webhook(drop_pending_updates=False)
            asyncio.create_task(runtime.dp.start_polling(runtime.bot, handle_signals=False))
            logger.info("telegram polling started")
    except Exception:
        logger.exception("bot failed to start")


async def _stop_bot() -> None:
    if runtime.dp is not None:
        try:
            await runtime.dp.stop_polling()
        except Exception:
            logger.info("polling was not running")
    if runtime.bot is not None:
        await runtime.bot.session.close()
        runtime.bot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    install_log_redaction(
        [
            settings.bot_token,
            settings.gofile_api_token,
            settings.database_url,
            settings.payment_card_number,
            settings.payment_card_name,
        ]
    )
    missing = missing_runtime_settings(settings)
    if missing:
        logger.warning("missing environment variables: %s", ", ".join(missing))
    if settings.webapp_url.startswith("https://") and settings.database_url.startswith("sqlite"):
        logger.warning("public WEBAPP_URL is set but DATABASE_URL is SQLite")
    expiration = None
    if not _under_pytest():
        expiration = asyncio.create_task(_expiration_loop())
        await _start_bot()
    yield
    if expiration is not None:
        expiration.cancel()
    await _stop_bot()


app = FastAPI(title="FAZO JUNATMA", lifespan=lifespan)
app.add_middleware(UploadSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        _settings.webapp_url.rstrip("/"),
        "https://web.telegram.org",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, **exc.extra})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    logger.exception("unhandled path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Ichki xatolik yuz berdi."})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/storage")
async def storage_page(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    return await storage.build_report(session)


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    from backend.utils.security import secrets_equal

    settings = get_settings()
    supplied = request.headers.get("x-telegram-bot-api-secret-token", "")
    expected = webhook_secret(settings.bot_token) if settings.bot_token else ""
    if not expected or not secrets_equal(supplied, expected):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    if runtime.bot is None or runtime.dp is None:
        return JSONResponse({"detail": "bot unavailable"}, status_code=503)
    try:
        payload = await request.json()
        update = Update.model_validate(payload)
    except Exception:
        logger.info("invalid telegram update")
        return JSONResponse({"detail": "bad update"}, status_code=400)
    try:
        await runtime.dp.feed_update(runtime.bot, update)
    except Exception:
        logger.exception("update handling failed")
        return JSONResponse({"ok": False}, status_code=500)
    return {"ok": True}


app.include_router(api_router, prefix="/api")

if (FRONTEND / "css").exists():
    app.mount("/css", StaticFiles(directory=FRONTEND / "css"), name="css")
if (FRONTEND / "js").exists():
    app.mount("/js", StaticFiles(directory=FRONTEND / "js"), name="js")


@app.get("/")
async def mini_app():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})
