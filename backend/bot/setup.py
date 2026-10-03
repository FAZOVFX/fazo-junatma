"""Dispatcher assembly. Imported by the web process, not by services."""

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot.admin import router as admin_router
from backend.bot.handlers import router as user_router
from backend.bot.payments import router as payment_router
from backend.bot.referral import router as referral_router
from backend.bot.subscriptions import router as subscription_router


def setup_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(admin_router)
    dispatcher.include_router(payment_router)
    dispatcher.include_router(subscription_router)
    dispatcher.include_router(referral_router)
    dispatcher.include_router(user_router)
    return dispatcher
