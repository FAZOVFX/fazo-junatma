"""Referral screen in the bot."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from backend.bot.keyboards import referral_keyboard
from backend.bot.panel import edit_panel, send_panel
from backend.database.database import session_scope
from backend.services.referral_service import current_bot_username, referral_link, referral_stats, register_user
from backend.texts import BTN_REFERRAL, referral_text

router = Router(name="referral")


@router.message(F.text == BTN_REFERRAL)
async def show_referral(message: Message) -> None:
    async with session_scope() as session:
        user, _created, _referrer = await register_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        stats = await referral_stats(session, user.id)
        link = referral_link(current_bot_username(), user.referral_code)
        text = referral_text(stats["invited_count"], stats["bonus_days"], link)
    await send_panel(message, f"<code>{link}</code>\n\n{text}", referral_keyboard(link))


@router.callback_query(F.data == "menu:ref")
async def menu_referral(callback: CallbackQuery) -> None:
    async with session_scope() as session:
        user, _created, _referrer = await register_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        stats = await referral_stats(session, user.id)
        link = referral_link(current_bot_username(), user.referral_code)
        text = referral_text(stats["invited_count"], stats["bonus_days"], link)
    await callback.answer()
    try:
        await edit_panel(callback.message, f"<code>{link}</code>\n\n{text}", referral_keyboard(link))
    except Exception:
        await send_panel(callback.message, f"<code>{link}</code>\n\n{text}", referral_keyboard(link))
