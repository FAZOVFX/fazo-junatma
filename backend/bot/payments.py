"""Manual payment flow inside the bot."""

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from backend.bot.keyboards import card_keyboard, main_menu, payment_amounts, payment_review, subscription_keyboard
from backend.bot.subscriptions import subscription_message
from backend.config import get_settings
from backend.constants import PAYMENT_PREMIUM, PAYMENT_WALLET, PREMIUM_PRICE_UZS
from backend.database.database import session_scope
from backend.database.models import User
from backend.services.errors import AppError
from backend.services.notifier import get_notifier
from backend.services.payment_service import manual_payments
from backend.services.referral_service import register_user
from backend.texts import (
    BTN_PAYMENT,
    CHOOSE_PAYMENT,
    RECEIPT_ACCEPTED,
    balance_text,
    card_charge_text,
    payment_card_text,
    payment_rejected,
    premium_approved,
    wallet_topup_approved,
)
from backend.utils.formatting import format_uzs

logger = logging.getLogger("fazo")
router = Router(name="payments")


class PayStates(StatesGroup):
    waiting_custom_amount = State()
    waiting_screenshot = State()


async def _user(message_user, session) -> User:
    user, _created, _referrer = await register_user(
        session,
        telegram_id=message_user.id,
        username=message_user.username,
        first_name=message_user.first_name,
        last_name=message_user.last_name,
    )
    return user


def _is_admin(telegram_id: int) -> bool:
    return telegram_id == get_settings().admin_telegram_id


async def _show_card(target: Message) -> None:
    settings = get_settings()
    await target.answer(payment_card_text(settings.payment_card_number, settings.payment_card_name))
    await target.answer(
        "To‘lov turini tanlang, so‘ng chek skrinshotini shu chatga yuboring.",
        reply_markup=payment_amounts(),
    )


@router.message(F.text == BTN_PAYMENT)
async def payment_menu(message: Message) -> None:
    async with session_scope() as session:
        user = await _user(message.from_user, session)
        is_admin = _is_admin(user.telegram_id)
    await _show_card(message)
    await message.answer("Asosiy menyu", reply_markup=main_menu(is_admin))


@router.message(F.text == "💰 Balans")
async def show_balance(message: Message) -> None:
    async with session_scope() as session:
        user = await _user(message.from_user, session)
        text = balance_text(user.balance_uzs)
        is_admin = _is_admin(user.telegram_id)
    await message.answer(text, reply_markup=payment_amounts())
    await message.answer("Asosiy menyu", reply_markup=main_menu(is_admin))


@router.callback_query(F.data == "sub:back")
async def subscription_back(callback: CallbackQuery) -> None:
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        logger.info("could not delete subscription message")


@router.callback_query(F.data == "sub:card")
async def subscription_card(callback: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    async with session_scope() as session:
        user = await _user(callback.from_user, session)
        try:
            payment = await manual_payments.create_payment(
                session,
                user,
                PAYMENT_PREMIUM,
                PREMIUM_PRICE_UZS,
                None,
                {"source": "bot"},
            )
        except AppError as exc:
            await callback.answer(exc.detail, show_alert=True)
            return
    await state.set_state(PayStates.waiting_screenshot)
    await state.update_data(payment_id=payment.id)
    await callback.answer()
    text = card_charge_text(payment.amount_uzs, settings.payment_card_number, settings.payment_card_name)
    try:
        await callback.message.edit_text(text, reply_markup=card_keyboard())
    except Exception:
        logger.info("could not edit subscription message id=%s", payment.id)
        await callback.message.answer(text, reply_markup=card_keyboard())
    logger.info("premium payment created id=%s user=%s", payment.id, callback.from_user.id)


@router.callback_query(F.data == "sub:offer")
async def subscription_offer(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = await subscription_message(callback.from_user)
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=subscription_keyboard())
    except Exception:
        logger.info("could not restore subscription message")


@router.callback_query(F.data.startswith("topup:"))
async def choose_amount(callback: CallbackQuery, state: FSMContext) -> None:
    choice = callback.data.split(":", 1)[1]
    if choice == "custom":
        await state.set_state(PayStates.waiting_custom_amount)
        await callback.answer()
        await callback.message.answer("Summani so‘mda yuboring. Bekor qilish uchun /cancel.")
        return
    if choice == "premium":
        payment_type = PAYMENT_PREMIUM
        amount = PREMIUM_PRICE_UZS
    else:
        payment_type = PAYMENT_WALLET
        amount = int(choice)
    async with session_scope() as session:
        user = await _user(callback.from_user, session)
        try:
            payment = await manual_payments.create_payment(
                session,
                user,
                payment_type,
                amount,
                None,
                {"source": "bot"},
            )
        except AppError as exc:
            await callback.answer(exc.detail, show_alert=True)
            return
    await state.set_state(PayStates.waiting_screenshot)
    await state.update_data(payment_id=payment.id)
    await callback.answer()
    await callback.message.answer(
        f"To‘lov yaratildi: {format_uzs(payment.amount_uzs)}\n\nChek skrinshotini shu chatga yuboring."
    )
    logger.info("payment created id=%s user=%s status=%s", payment.id, callback.from_user.id, payment.status)


@router.message(PayStates.waiting_custom_amount, F.text)
async def custom_amount(message: Message, state: FSMContext) -> None:
    digits = re.sub(r"[^\d]", "", message.text or "")
    if not digits:
        await message.answer("Summani raqam bilan yuboring.")
        return
    amount = int(digits)
    async with session_scope() as session:
        user = await _user(message.from_user, session)
        try:
            payment = await manual_payments.create_payment(
                session,
                user,
                PAYMENT_WALLET,
                amount,
                None,
                {"source": "bot"},
            )
        except AppError as exc:
            await message.answer(exc.detail)
            return
    await state.set_state(PayStates.waiting_screenshot)
    await state.update_data(payment_id=payment.id)
    await message.answer(f"Summa: {format_uzs(payment.amount_uzs)}\n\nChek skrinshotini shu chatga yuboring.")


@router.message(Command("cancel"))
async def cancel_payment(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


async def _accept_screenshot(message: Message, file_id: str, state: FSMContext) -> None:
    data = await state.get_data()
    payment_id = data.get("payment_id")
    async with session_scope() as session:
        user = await _user(message.from_user, session)
        if _is_admin(user.telegram_id) and not payment_id:
            pending = await manual_payments.get_pending_payments(session, limit=1)
            if not any(item.user_id == user.id and item.screenshot_file_id is None for item in pending):
                return
        payment, attached = await manual_payments.attach_screenshot(session, user, file_id, payment_id)
        if payment is None:
            await message.answer(CHOOSE_PAYMENT, reply_markup=payment_amounts())
            return
        user_row = await session.get(User, payment.user_id)
        caption = (
            "💳 Yangi to‘lov cheki\n\n"
            f"Foydalanuvchi: {user_row.telegram_id}\n"
            f"Summa: {format_uzs(payment.amount_uzs)}\n"
            f"Turi: {payment.type}\n"
            f"Holat: {payment.status}\n"
            f"To‘lov: {payment.id}"
        )
    await state.clear()
    await message.answer(RECEIPT_ACCEPTED)
    settings = get_settings()
    await get_notifier().send_photo(
        settings.admin_telegram_id,
        file_id,
        caption,
        reply_markup=payment_review(payment.id),
    )
    logger.info("screenshot stored payment=%s user=%s attached=%s", payment.id, message.from_user.id, attached)


@router.message(F.photo)
async def on_photo(message: Message, state: FSMContext) -> None:
    await _accept_screenshot(message, message.photo[-1].file_id, state)


@router.message(F.document)
async def on_document(message: Message, state: FSMContext) -> None:
    mime = message.document.mime_type or ""
    if not mime.startswith("image/"):
        return
    await _accept_screenshot(message, message.document.file_id, state)


async def _apply_review(callback: CallbackQuery, approve: bool) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin huquqi yo‘q.", show_alert=True)
        return
    payment_id = int(callback.data.rsplit(":", 1)[1])
    async with session_scope() as session:
        try:
            if approve:
                result = await manual_payments.approve_payment(session, payment_id, callback.from_user.id)
            else:
                result = await manual_payments.reject_payment(session, payment_id, callback.from_user.id)
        except AppError as exc:
            await callback.answer(exc.detail, show_alert=True)
            return
    if result["result"] in {"already_approved", "already_rejected"}:
        await callback.answer("Bu to‘lov allaqachon ko‘rib chiqilgan.", show_alert=True)
        return
    if result["result"] == "approved" and result["type"] == "premium":
        text = premium_approved()
    elif result["result"] == "approved":
        text = wallet_topup_approved(result["amount_uzs"], result["balance_uzs"])
    else:
        text = payment_rejected()
    await get_notifier().send_message(result["user_telegram_id"], text)
    await callback.answer("Saqlandi")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.info("could not clear payment keyboard id=%s", payment_id)
    logger.info(
        "payment %s id=%s admin=%s user=%s",
        result["result"],
        payment_id,
        callback.from_user.id,
        result["user_telegram_id"],
    )


@router.callback_query(F.data.startswith("pay:ok:"))
async def approve(callback: CallbackQuery) -> None:
    await _apply_review(callback, True)


@router.callback_query(F.data.startswith("pay:no:"))
async def reject(callback: CallbackQuery) -> None:
    await _apply_review(callback, False)
