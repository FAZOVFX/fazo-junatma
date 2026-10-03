"""User menu, start command, and handler errors."""

import logging

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import ErrorEvent, Message

from backend.bot.keyboards import NO_PREVIEW, main_menu, open_app, shared_file_keyboard
from backend.config import get_settings
from backend.database.database import session_scope
from backend.services import file_service
from backend.services.errors import AppError
from backend.services.referral_service import parse_referral_payload, referral_stats, register_user
from backend.services.subscription_service import sync_subscription_status
from backend.texts import BTN_BALANCE, BTN_FILES, BTN_HELP, BTN_UPLOAD, account_text, file_ready_text, help_text, welcome_text
from backend.utils.formatting import utcnow

logger = logging.getLogger("fazo")
router = Router(name="user")


async def _send_shared_file(message: Message, code: str, is_admin: bool) -> None:
    async with session_scope() as session:
        try:
            info = await file_service.get_public_file(session, code)
        except AppError as exc:
            await message.answer(exc.detail, reply_markup=main_menu(is_admin))
            return
    await message.answer(
        file_ready_text(
            info["file_name"],
            info["file_size_text"],
            info["share_url"],
            info["page_url"],
            info["download_url"] or "",
        ),
        reply_markup=shared_file_keyboard(info["page_url"], info["download_url"]),
        link_preview_options=NO_PREVIEW,
    )
    await message.answer("Boshlash uchun pastdagi tugmani bosing.", reply_markup=main_menu(is_admin))


@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    now = utcnow()
    file_code = file_service.parse_file_code(command.args)
    referral = None if file_code else parse_referral_payload(command.args)
    async with session_scope() as session:
        user, created, _referrer = await register_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            referral_code=referral,
            now=now,
        )
        sync_subscription_status(user, now)
        await session.commit()
        is_admin = user.telegram_id == get_settings().admin_telegram_id
        text = welcome_text(
            message.from_user.first_name or "do‘st",
            user.subscription_status,
            user.subscription_expires_at,
            now,
        )
        if created and referral:
            text += "\n\nReferal havola orqali kirdingiz."
    if file_code:
        await _send_shared_file(message, file_code, is_admin)
        logger.info("start file user=%s created=%s", message.from_user.id, created)
        return
    await message.answer(text, reply_markup=main_menu(is_admin))
    logger.info("start user=%s created=%s", message.from_user.id, created)


@router.message(F.text == BTN_HELP)
async def help_message(message: Message) -> None:
    is_admin = message.from_user.id == get_settings().admin_telegram_id
    await message.answer(help_text(), reply_markup=main_menu(is_admin))


@router.message(F.text.in_({BTN_UPLOAD, "📤 Fayl yuklash"}))
async def upload_hint(message: Message) -> None:
    button = open_app("upload", BTN_UPLOAD)
    if button is None:
        await message.answer(
            "Fayl yuklash Mini App orqali ochiladi. WEBAPP_URL https bo‘lishi kerak.",
            reply_markup=main_menu(message.from_user.id == get_settings().admin_telegram_id),
        )
        return
    await message.answer("Faylni Mini App orqali yuklang.", reply_markup=button)


@router.message(F.text == BTN_BALANCE)
async def account(message: Message) -> None:
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
        stats = await referral_stats(session, user.id)
        files = await file_service.count_files(session, user.id)
        await session.commit()
        text = account_text(
            user.telegram_id,
            user.subscription_status,
            user.subscription_expires_at,
            now,
            stats["invited_count"],
            files,
            user.balance_uzs,
        )
        is_admin = user.telegram_id == get_settings().admin_telegram_id
    await message.answer(text, reply_markup=main_menu(is_admin))


@router.message(F.text == BTN_FILES)
async def files_hint(message: Message) -> None:
    button = open_app("files", BTN_FILES)
    if button is None:
        await message.answer(
            "Fayllar Mini App ichida. WEBAPP_URL https bo‘lishi kerak.",
            reply_markup=main_menu(message.from_user.id == get_settings().admin_telegram_id),
        )
        return
    await message.answer("Fayllaringiz Mini App ichida.", reply_markup=button)


@router.error()
async def on_error(event: ErrorEvent) -> bool:
    update = event.update
    update_id = getattr(update, "update_id", None)
    logger.exception("bot handler error update_id=%s", update_id)
    message = update.message if update else None
    if message is None and update and update.callback_query:
        message = update.callback_query.message
    if message is not None:
        try:
            await message.answer("Xatolik yuz berdi. Qayta urinib ko‘ring.")
        except Exception:
            logger.exception("failed to send error reply")
    return True
