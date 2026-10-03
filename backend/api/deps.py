"""Authentication dependencies. Identity comes only from verified initData."""

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.database.database import get_session
from backend.database.models import User
from backend.services.referral_service import parse_referral_payload, register_user
from backend.services.storage_service import StorageService, get_storage
from backend.utils.security import rate_limit_allow
from backend.utils.telegram_auth import AuthError, verify_init_data


def get_storage_dep() -> StorageService:
    return get_storage()


def _init_data_from_headers(x_telegram_init_data: str | None, authorization: str | None) -> str:
    if x_telegram_init_data:
        return x_telegram_init_data
    if authorization and authorization.lower().startswith("tma "):
        return authorization[4:]
    return ""


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_telegram_init_data: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    ip = request.client.host if request.client else "unknown"
    if not rate_limit_allow(f"ip:{ip}", 600, 60):
        raise HTTPException(status_code=429, detail="Juda ko‘p so‘rov. Biroz kuting.")
    init_data = _init_data_from_headers(x_telegram_init_data, authorization)
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram autentifikatsiyasi talab qilinadi.")
    settings = get_settings()
    try:
        parsed = verify_init_data(init_data, settings.bot_token)
    except AuthError:
        if not rate_limit_allow(f"auth-fail:{ip}", 30, 60):
            raise HTTPException(status_code=429, detail="Juda ko‘p so‘rov. Biroz kuting.")
        raise HTTPException(status_code=401, detail="Telegram autentifikatsiyasi yaroqsiz.")
    if not rate_limit_allow(f"user:{parsed['id']}", 120, 60):
        raise HTTPException(status_code=429, detail="Juda ko‘p so‘rov. Biroz kuting.")
    referral = parse_referral_payload(parsed.get("start_param"))
    user, _created, _referrer = await register_user(
        session,
        telegram_id=parsed["id"],
        username=parsed.get("username"),
        first_name=parsed.get("first_name"),
        last_name=parsed.get("last_name"),
        referral_code=referral,
    )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.telegram_id != get_settings().admin_telegram_id:
        raise HTTPException(status_code=403, detail="Admin huquqi yo‘q.")
    return user
