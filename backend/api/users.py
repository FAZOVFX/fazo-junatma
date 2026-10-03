"""Current user, wallet, and referral."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user
from backend.config import get_settings
from backend.constants import EXTENSION_PRICE_UZS, REFERRAL_REWARD_DAYS
from backend.database.database import get_session
from backend.database.models import User
from backend.services.referral_service import current_bot_username, referral_link, referral_stats
from backend.services.subscription_service import sync_subscription_status
from backend.services.wallet_service import list_transactions
from backend.texts import access_pill
from backend.utils.formatting import as_utc, format_duration, format_uzs, status_label, utcnow

router = APIRouter(tags=["users"])


def me_payload(user: User) -> dict:
    now = utcnow()
    sync_subscription_status(user, now)
    remaining = as_utc(user.subscription_expires_at) - now
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "balance_uzs": user.balance_uzs,
        "balance_text": format_uzs(user.balance_uzs),
        "subscription_status": user.subscription_status,
        "subscription_label": status_label(user.subscription_status),
        "remaining_text": format_duration(remaining),
        "access_text": access_pill(user.subscription_status, user.subscription_expires_at, now),
        "is_trial": user.subscription_status == "trial",
        "is_admin": user.telegram_id == get_settings().admin_telegram_id,
        "subscription_expires_at": as_utc(user.subscription_expires_at).isoformat(),
        "referral_code": user.referral_code,
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    payload = me_payload(user)
    await session.commit()
    return payload


@router.get("/wallet")
async def wallet(user: User = Depends(get_current_user)):
    return {
        "balance_uzs": user.balance_uzs,
        "balance_text": format_uzs(user.balance_uzs),
        "extension_price_uzs": EXTENSION_PRICE_UZS,
        "extension_price_text": format_uzs(EXTENSION_PRICE_UZS),
    }


@router.get("/wallet/transactions")
async def wallet_transactions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = await list_transactions(session, user.id)
    return {
        "items": [
            {
                "id": row.id,
                "type": row.type,
                "amount_uzs": row.amount_uzs,
                "amount_text": format_uzs(row.amount_uzs),
                "balance_before": row.balance_before,
                "balance_after": row.balance_after,
                "description": row.description,
                "payment_id": row.payment_id,
                "created_at": as_utc(row.created_at).isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/referral")
async def referral(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stats = await referral_stats(session, user.id)
    username = current_bot_username()
    return {
        "referral_code": user.referral_code,
        "invited_count": stats["invited_count"],
        "bonus_days": stats["bonus_days"],
        "reward_days_each": REFERRAL_REWARD_DAYS,
        "link": referral_link(username, user.referral_code),
        "bot_username": username or None,
    }
