"""Premium screen in the bot."""

from aiogram import F, Router
from aiogram.types import Message

from backend.bot.keyboards import main_menu, payment_amounts
from backend.config import get_settings
from backend.database.database import session_scope
from backend.services.referral_service import register_user
from backend.services.subscription_service import sync_subscription_status
from backend.texts import BTN_PREMIUM, payment_card_text, premium_text
from backend.utils.formatting import as_utc, utcnow

router = Router(name="subscriptions")


@router.message(F.text == BTN_PREMIUM)
async def show_premium(message: Message) -> None:
    now = utcnow()
    async with session_scope() as session:
        user, _created, _referrer = await register_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        sync_subscription_status(user, now)
        await session.commit()
        remaining = as_utc(user.subscription_expires_at) - now
        text = premium_text(user.subscription_status, remaining)
        is_admin = user.telegram_id == get_settings().admin_telegram_id
    settings = get_settings()
    await message.answer(
        text + "\n\n" + payment_card_text(settings.payment_card_number, settings.payment_card_name),
        reply_markup=payment_amounts(),
    )
    await message.answer("Asosiy menyu", reply_markup=main_menu(is_admin))
