"""Main screen text and the inline menu that sits on the message."""

from aiogram.types import Message

from backend.bot.keyboards import HIDE_REPLY_KEYBOARD
from backend.config import get_settings
from backend.database.database import session_scope
from backend.services.referral_service import register_user
from backend.services.subscription_service import sync_subscription_status
from backend.texts import welcome_text
from backend.utils.formatting import utcnow


async def home_content(telegram_user) -> tuple[str, bool]:
    now = utcnow()
    async with session_scope() as session:
        user, _created, _referrer = await register_user(
            session,
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )
        sync_subscription_status(user, now)
        await session.commit()
        is_admin = user.telegram_id == get_settings().admin_telegram_id
        text = welcome_text(
            telegram_user.first_name or "do‘st",
            user.subscription_status,
            user.subscription_expires_at,
            now,
        )
    return text, is_admin


async def send_panel(message: Message, text: str, markup, **kwargs):
    """Drop the bottom reply keyboard, then pin the buttons under this message."""
    sent = await message.answer(text, reply_markup=HIDE_REPLY_KEYBOARD, **kwargs)
    if markup is not None:
        await sent.edit_reply_markup(reply_markup=markup)
    return sent


async def edit_panel(message: Message, text: str, markup) -> None:
    await message.edit_text(text, reply_markup=markup)
