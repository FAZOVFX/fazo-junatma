"""Admin panel. Only ADMIN_TELEGRAM_ID can open it."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from backend.bot.keyboards import admin_menu, main_menu, payment_review
from backend.config import get_settings
from backend.database.database import session_scope
from backend.database.models import User
from backend.services.admin_service import list_users, list_wallet_operations, statistics
from backend.services.payment_service import manual_payments
from backend.services.storage_service import get_storage
from backend.texts import BTN_ADMIN
from backend.utils.formatting import format_uzs, status_label

logger = logging.getLogger("fazo")
router = Router(name="admin")


def _is_admin(telegram_id: int) -> bool:
    return telegram_id == get_settings().admin_telegram_id


@router.message(F.text == BTN_ADMIN)
async def open_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Admin huquqi yo‘q.")
        return
    await message.answer("👑 Admin panel", reply_markup=admin_menu())


def _storage_text(report: dict) -> str:
    return (
        "📦 Storage\n\n"
        f"Faol fayllar:\n{report['active_files']}\n\n"
        f"Faol hajm:\n{report['active_size_text']}\n\n"
        f"Configured limit:\n{report['configured_limit_text']}\n\n"
        f"Usage:\n{report['usage_percent']}%\n\n"
        f"Remaining:\n{report['remaining_text']}\n\n"
        f"Expired:\n{report['expired_files']}\n\n"
        f"Deleted:\n{report['deleted_files']}"
    )


@router.callback_query(F.data == "adm:payments")
async def pending_payments(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin huquqi yo‘q.", show_alert=True)
        return
    await callback.answer()
    async with session_scope() as session:
        rows = await manual_payments.get_pending_payments(session, limit=10)
        payloads = []
        for payment in rows:
            user = await session.get(User, payment.user_id)
            payloads.append((payment, user))
    if not payloads:
        await callback.message.answer("Kutilayotgan to‘lovlar yo‘q.")
        return
    for payment, user in payloads:
        text = (
            "💳 Kutilayotgan to‘lov\n\n"
            f"Foydalanuvchi: {user.first_name if user else '-'}\n"
            f"Telegram ID: {user.telegram_id if user else '-'}\n"
            f"Summa: {format_uzs(payment.amount_uzs)}\n"
            f"Turi: {payment.type}\n"
            f"Yaratilgan: {payment.created_at}\n"
            f"Holat: {payment.status}"
        )
        markup = payment_review(payment.id)
        if payment.screenshot_file_id:
            await callback.message.answer_photo(payment.screenshot_file_id, caption=text, reply_markup=markup)
        else:
            await callback.message.answer(text + "\n\nSkrinshot hali yo‘q.", reply_markup=markup)


@router.callback_query(F.data == "adm:users")
async def users(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin huquqi yo‘q.", show_alert=True)
        return
    await callback.answer()
    async with session_scope() as session:
        rows = await list_users(session, limit=15)
    if not rows:
        await callback.message.answer("Foydalanuvchilar yo‘q.")
        return
    lines = ["👥 Foydalanuvchilar\n"]
    for user in rows:
        lines.append(
            f"{user.telegram_id} · {user.first_name or '-'} · {status_label(user.subscription_status)} · {format_uzs(user.balance_uzs)}"
        )
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "adm:storage")
async def storage(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin huquqi yo‘q.", show_alert=True)
        return
    await callback.answer()
    async with session_scope() as session:
        report = await get_storage().build_report(session)
    await callback.message.answer(_storage_text(report))


@router.callback_query(F.data == "adm:wallet")
async def wallet_ops(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin huquqi yo‘q.", show_alert=True)
        return
    await callback.answer()
    async with session_scope() as session:
        rows = await list_wallet_operations(session, limit=15)
    if not rows:
        await callback.message.answer("Balans operatsiyalari yo‘q.")
        return
    lines = ["💰 Balans operatsiyalari\n"]
    for row in rows:
        lines.append(f"#{row.id} {row.type} {format_uzs(row.amount_uzs)} → {format_uzs(row.balance_after)}")
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "adm:stats")
async def stats(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Admin huquqi yo‘q.", show_alert=True)
        return
    await callback.answer()
    async with session_scope() as session:
        data = await statistics(session, get_storage())
    text = (
        "📊 Statistika\n\n"
        f"Foydalanuvchilar: {data['users_total']}\n"
        f"Trial: {data['users_trial']}\n"
        f"Faol: {data['users_active']}\n"
        f"Tugagan: {data['users_expired']}\n"
        f"Faol fayllar: {data['files_active']}\n"
        f"Kutilayotgan to‘lovlar: {data['payments_pending']}\n"
        f"Tasdiqlangan summa: {format_uzs(data['approved_amount_uzs'])}\n"
        f"Referallar: {data['referrals_total']}"
    )
    await callback.message.answer(text)


@router.message(F.text == "/admin")
async def admin_command(message: Message) -> None:
    await open_admin(message)
    if _is_admin(message.from_user.id):
        await message.answer("Menyu", reply_markup=main_menu(True))
