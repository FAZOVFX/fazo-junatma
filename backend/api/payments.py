"""Manual payments. Screenshots stay pending until an admin reviews them."""

import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, require_admin
from backend.bot import runtime
from backend.config import get_settings
from backend.constants import EXTENSION_PRICE_UZS, PREMIUM_DAYS, PREMIUM_PRICE_UZS, TOPUP_PRESETS_UZS
from backend.database.database import get_session
from backend.database.models import Payment, User
from backend.database.schemas import PaymentCreateRequest
from backend.services.errors import AppError
from backend.services.notifier import get_notifier
from backend.services.payment_service import manual_payments
from backend.texts import RECEIPT_ACCEPTED, payment_card_text, payment_rejected, premium_approved, wallet_topup_approved
from backend.utils.formatting import as_utc, format_uzs
from backend.utils.security import rate_limit_allow, sanitize_filename

logger = logging.getLogger("fazo")
router = APIRouter(tags=["payments"])


def _payment_dict(payment: Payment, include_reviewer: bool = False) -> dict:
    payload = {
        "id": payment.id,
        "type": payment.type,
        "amount_uzs": payment.amount_uzs,
        "amount_text": format_uzs(payment.amount_uzs),
        "method": payment.method,
        "status": payment.status,
        "description": payment.description,
        "has_screenshot": bool(payment.screenshot_file_id),
        "created_at": as_utc(payment.created_at).isoformat(),
        "reviewed_at": as_utc(payment.reviewed_at).isoformat() if payment.reviewed_at else None,
    }
    if include_reviewer:
        payload["reviewed_by"] = payment.reviewed_by
        payload["screenshot_file_id"] = payment.screenshot_file_id
        payload["user_id"] = payment.user_id
    return payload


@router.get("/payments")
async def payment_home(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    settings = get_settings()
    rows = await manual_payments.list_user_payments(session, user.id)
    return {
        "card_number": settings.payment_card_number,
        "card_name": settings.payment_card_name,
        "card_text": payment_card_text(settings.payment_card_number, settings.payment_card_name),
        "premium_price_uzs": PREMIUM_PRICE_UZS,
        "premium_price_text": format_uzs(PREMIUM_PRICE_UZS),
        "premium_days": PREMIUM_DAYS,
        "extension_price_uzs": EXTENSION_PRICE_UZS,
        "extension_price_text": format_uzs(EXTENSION_PRICE_UZS),
        "topup_presets_uzs": list(TOPUP_PRESETS_UZS),
        "payments": [_payment_dict(row) for row in rows],
    }


@router.post("/payments")
async def create_payment(
    body: PaymentCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not rate_limit_allow(f"payment:{user.telegram_id}", 10, 3600):
        raise AppError(429, "Juda ko‘p to‘lov so‘rovi. Biroz kuting.")
    payment = await manual_payments.create_payment(
        session,
        user,
        body.type,
        body.amount_uzs,
        body.description,
        {"source": "miniapp"},
    )
    logger.info("payment created id=%s user=%s type=%s status=%s", payment.id, user.telegram_id, payment.type, payment.status)
    return _payment_dict(payment)


@router.post("/payments/screenshot")
async def upload_screenshot(
    payment_id: int = Form(...),
    screenshot: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    content_type = screenshot.content_type or ""
    if not content_type.startswith("image/"):
        raise AppError(422, "Chek sifatida rasm yuboring.")
    data = await screenshot.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise AppError(413, "Skrinshot hajmi juda katta.")
    if runtime.bot is None:
        raise AppError(503, "Skrinshotni bot chatiga yuboring.")
    from aiogram.types import BufferedInputFile

    filename = sanitize_filename(screenshot.filename or "chek.jpg")
    sent = await runtime.bot.send_photo(
        get_settings().admin_telegram_id,
        BufferedInputFile(data, filename=filename),
        caption=f"Chek kutilmoqda\nFoydalanuvchi: {user.telegram_id}",
    )
    file_id = sent.photo[-1].file_id if sent and sent.photo else None
    if not file_id:
        raise AppError(502, "Chekni qabul qilib bo‘lmadi. Bot chatiga yuboring.")
    payment, attached = await manual_payments.attach_screenshot(session, user, file_id, payment_id)
    if payment is None:
        raise AppError(404, "To‘lov topilmadi.")
    logger.info("screenshot stored payment=%s user=%s", payment.id, user.telegram_id)
    return {"status": payment.status, "payment_id": payment.id, "attached": attached, "message": RECEIPT_ACCEPTED}


async def _notify_decision(result: dict) -> None:
    if result["result"] == "approved" and result["type"] == "premium":
        text = premium_approved()
    elif result["result"] == "approved" and result["type"] == "wallet_topup":
        text = wallet_topup_approved(result["amount_uzs"], result["balance_uzs"])
    elif result["result"] == "rejected":
        text = payment_rejected()
    else:
        return
    await get_notifier().send_message(result["user_telegram_id"], text)


@router.get("/admin/payments")
async def admin_payments(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = await manual_payments.get_pending_payments(session)
    items = []
    for payment in rows:
        user = await session.get(User, payment.user_id)
        item = _payment_dict(payment, include_reviewer=True)
        item["telegram_id"] = user.telegram_id if user else None
        item["username"] = user.username if user else None
        item["first_name"] = user.first_name if user else None
        items.append(item)
    return {"items": items}


@router.post("/admin/payments/{payment_id}/approve")
async def approve_payment(
    payment_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await manual_payments.approve_payment(session, payment_id, admin.telegram_id)
    if result["result"] == "approved":
        logger.info(
            "payment approved id=%s admin=%s user=%s",
            payment_id,
            admin.telegram_id,
            result["user_telegram_id"],
        )
        await _notify_decision(result)
    return result


@router.post("/admin/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await manual_payments.reject_payment(session, payment_id, admin.telegram_id)
    if result["result"] == "rejected":
        logger.info(
            "payment rejected id=%s admin=%s user=%s",
            payment_id,
            admin.telegram_id,
            result["user_telegram_id"],
        )
        await _notify_decision(result)
    return result
