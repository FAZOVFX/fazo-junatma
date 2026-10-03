"""Premium screen in the bot."""

from aiogram import F, Router
from aiogram.types import Message

from backend.bot.keyboards import payment_amounts, subscription_keyboard
from backend.constants import EXTENSION_PRICE_UZS
from backend.database.database import session_scope
from backend.services.referral_service import register_user
from backend.services.subscription_service import sync_subscription_status
from backend.texts import BTN_PREMIUM, premium_text
from backend.utils.formatting import format_uzs, utcnow

router = Router(name="subscriptions")


@router.message(F.text.in_({BTN_PREMIUM, "💎 Premium"}))
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
        text = premium_text(user.subscription_status, user.subscription_expires_at, now)
    await message.answer(text, reply_markup=subscription_keyboard())
    await message.answer(
        "💰 Balans\n\n"
        f"Faylni 24 soatga uzaytirish: {format_uzs(EXTENSION_PRICE_UZS)}.\n"
        "Balans faqat fayl muddatini uzaytirish uchun ishlatiladi.",
        reply_markup=payment_amounts(),
    )
