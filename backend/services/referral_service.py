"""Registration, one-time trial, and one-time referral rewards."""

import re
import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.bot import runtime
from backend.constants import REFERRAL_REWARD_DAYS
from backend.database.models import Referral, User
from backend.services.locks import resource_lock
from backend.services.notifier import get_notifier
from backend.services.subscription_service import add_referral_day, apply_trial, sync_subscription_status
from backend.texts import referral_reward_notice
from backend.utils.formatting import as_utc, utcnow

_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")


def new_referral_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


def referral_link(username: str, code: str) -> str:
    name = username or "BOT_USERNAME"
    return f"https://t.me/{name}?start=ref_{code}"


def parse_referral_payload(payload: str | None) -> str | None:
    if not payload:
        return None
    value = payload.strip()
    if value.startswith("f_"):
        return None
    if value.startswith("ref_"):
        value = value[4:]
    if not _CODE_RE.fullmatch(value):
        return None
    return value


async def award_referral(session: AsyncSession, new_user: User, code: str | None, now) -> User | None:
    parsed = parse_referral_payload(code)
    if not parsed:
        return None
    referrer = await session.scalar(select(User).where(User.referral_code == parsed))
    if referrer is None:
        return None
    if referrer.id == new_user.id or referrer.telegram_id == new_user.telegram_id:
        return None
    referral = Referral(
        referrer_user_id=referrer.id,
        referred_user_id=new_user.id,
        reward_days=REFERRAL_REWARD_DAYS,
        created_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(referral)
            await session.flush()
    except IntegrityError:
        return None
    new_user.referred_by = referrer.id
    add_referral_day(referrer, now)
    return referrer


async def register_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    referral_code: str | None = None,
    now=None,
) -> tuple[User, bool, User | None]:
    now = now or utcnow()
    async with resource_lock("register", telegram_id):
        existing = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if existing is not None:
            existing.username = username
            existing.first_name = first_name
            existing.last_name = last_name
            sync_subscription_status(existing, now)
            existing.updated_at = now
            await session.commit()
            return existing, False, None

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            referral_code=new_referral_code(),
            referred_by=None,
            balance_uzs=0,
            created_at=now,
            updated_at=now,
        )
        apply_trial(user, now)
        session.add(user)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            if existing is None:
                raise
            return existing, False, None

        rewarded = await award_referral(session, user, referral_code, now)
        await session.commit()

    if rewarded is not None:
        remaining = as_utc(rewarded.subscription_expires_at) - now
        await get_notifier().send_message(rewarded.telegram_id, referral_reward_notice(remaining))
    return user, True, rewarded


async def referral_stats(session: AsyncSession, user_id: int) -> dict:
    invited = int(
        await session.scalar(
            select(func.count(Referral.id)).where(Referral.referrer_user_id == user_id)
        )
        or 0
    )
    bonus = int(
        await session.scalar(
            select(func.coalesce(func.sum(Referral.reward_days), 0)).where(Referral.referrer_user_id == user_id)
        )
        or 0
    )
    return {"invited_count": invited, "bonus_days": bonus}


def current_bot_username() -> str:
    return runtime.bot_username or ""
