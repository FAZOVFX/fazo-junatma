"""Referral screen in the bot."""

from aiogram import F, Router
from aiogram.types import Message

from backend.bot.keyboards import main_menu, referral_keyboard
from backend.config import get_settings
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
        is_admin = user.telegram_id == get_settings().admin_telegram_id
        text = referral_text(stats["invited_count"], stats["bonus_days"], link)
    await message.answer(f"<code>{link}</code>\n\n{text}", reply_markup=referral_keyboard(link))
    await message.answer("Asosiy menyu", reply_markup=main_menu(is_admin))
