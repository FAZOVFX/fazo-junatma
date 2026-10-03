"""Telegram keyboards."""

from urllib.parse import quote

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    LinkPreviewOptions,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from backend.config import get_settings
from backend.texts import (
    BTN_ADMIN,
    BTN_BACK,
    BTN_BALANCE,
    BTN_CARD,
    BTN_PREMIUM,
    BTN_REFERRAL,
    BTN_UPLOAD,
)


def _webapp(screen: str) -> str | None:
    base = get_settings().webapp_url.rstrip("/")
    if not base.startswith("https://"):
        return None
    if screen in {"", "upload", "home"}:
        return f"{base}/"
    return f"{base}/?screen={screen}"


def main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    upload_url = _webapp("upload")
    upload_button = (
        KeyboardButton(text=BTN_UPLOAD, web_app=WebAppInfo(url=upload_url))
        if upload_url
        else KeyboardButton(text=BTN_UPLOAD)
    )
    rows = [
        [upload_button],
        [KeyboardButton(text=BTN_PREMIUM), KeyboardButton(text=BTN_REFERRAL)],
        [KeyboardButton(text=BTN_BALANCE)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BTN_CARD, callback_data="sub:card")],
            [InlineKeyboardButton(text=BTN_BACK, callback_data="sub:back")],
        ]
    )


def card_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BTN_BACK, callback_data="sub:offer")]]
    )


def file_ready_keyboard(share_url: str) -> InlineKeyboardMarkup:
    share = f"https://t.me/share/url?url={quote(share_url, safe='')}&text={quote('Faylni oching', safe='')}"
    upload_url = _webapp("upload")
    rows = [[InlineKeyboardButton(text="↗️ Do'stga yuborish", url=share)]]
    if upload_url:
        rows.append([InlineKeyboardButton(text=BTN_UPLOAD, web_app=WebAppInfo(url=upload_url))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shared_file_keyboard(page_url: str | None, gofile_url: str | None) -> InlineKeyboardMarkup:
    rows = []
    if page_url and page_url.startswith("https://"):
        rows.append([InlineKeyboardButton(text="📄 Faylni ochish", web_app=WebAppInfo(url=page_url))])
    if gofile_url and gofile_url.startswith("https://"):
        rows.append([InlineKeyboardButton(text="🌐 Brauzerda ochish", url=gofile_url)])
    upload_url = _webapp("upload")
    if upload_url:
        rows.append([InlineKeyboardButton(text=BTN_UPLOAD, web_app=WebAppInfo(url=upload_url))])
    if not rows:
        rows.append([InlineKeyboardButton(text=BTN_BACK, callback_data="sub:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


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
