"""Premium screen in the bot."""

from aiogram import F, Router
from aiogram.types import Message, User as TelegramUser

from backend.bot.keyboards import subscription_keyboard
from backend.database.database import session_scope
from backend.services.referral_service import register_user
from backend.services.subscription_service import sync_subscription_status
from backend.texts import BTN_PREMIUM, premium_text
from backend.utils.formatting import utcnow

router = Router(name="subscriptions")


async def subscription_message(telegram_user: TelegramUser) -> str:
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
        return premium_text(
            user.subscription_status,
            user.subscription_expires_at,
            now,
            user.balance_uzs,
        )


@router.message(F.text.in_({BTN_PREMIUM, "💎 Premium"}))
async def show_premium(message: Message) -> None:
    text = await subscription_message(message.from_user)
    await message.answer(text, reply_markup=subscription_keyboard())
