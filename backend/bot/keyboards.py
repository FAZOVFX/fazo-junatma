"""Telegram keyboards."""

from urllib.parse import quote

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from backend.config import get_settings
from backend.texts import (
    BTN_ADMIN,
    BTN_BALANCE,
    BTN_FILES,
    BTN_HELP,
    BTN_PAYMENT,
    BTN_PREMIUM,
    BTN_REFERRAL,
    BTN_UPLOAD,
)


def _webapp(screen: str) -> str | None:
    base = get_settings().webapp_url.rstrip("/")
    if not base.startswith("https://"):
        return None
    return f"{base}/#{screen}"


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    upload_url = _webapp("upload")
    files_url = _webapp("files")
    upload_button = (
        KeyboardButton(text=BTN_UPLOAD, web_app=WebAppInfo(url=upload_url))
        if upload_url
        else KeyboardButton(text=BTN_UPLOAD)
    )
    files_button = (
        KeyboardButton(text=BTN_FILES, web_app=WebAppInfo(url=files_url))
        if files_url
        else KeyboardButton(text=BTN_FILES)
    )
    rows = [
        [upload_button, files_button],
        [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_PREMIUM)],
        [KeyboardButton(text=BTN_REFERRAL), KeyboardButton(text=BTN_PAYMENT)],
        [KeyboardButton(text=BTN_HELP)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def payment_amounts() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 000 so‘m", callback_data="topup:5000"),
                InlineKeyboardButton(text="10 000 so‘m", callback_data="topup:10000"),
            ],
            [
                InlineKeyboardButton(text="15 000 so‘m", callback_data="topup:15000"),
                InlineKeyboardButton(text="20 000 so‘m", callback_data="topup:20000"),
            ],
            [InlineKeyboardButton(text="Boshqa summa", callback_data="topup:custom")],
            [InlineKeyboardButton(text="💎 Premium 15 000", callback_data="topup:premium")],
        ]
    )


def referral_keyboard(link: str) -> InlineKeyboardMarkup:
    share = f"https://t.me/share/url?url={quote(link, safe='')}&text={quote('FAZO JUNATMA')}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Ulashish", url=share)],
            [InlineKeyboardButton(text="📋 Nusxa olish", copy_text=CopyTextButton(text=link))],
        ]
    )


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Kutilayotgan to‘lovlar", callback_data="adm:payments")],
            [InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="adm:users")],
            [InlineKeyboardButton(text="📁 Storage", callback_data="adm:storage")],
            [InlineKeyboardButton(text="💰 Balans operatsiyalari", callback_data="adm:wallet")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stats")],
        ]
    )


def payment_review(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay:ok:{payment_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay:no:{payment_id}"),
            ]
        ]
    )


def open_app(screen: str, label: str) -> InlineKeyboardMarkup | None:
    url = _webapp(screen)
    if not url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )
