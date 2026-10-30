"""Uploads.

The Mini App first asks for a one-time ticket (login, subscription and size are checked
there), then sends the raw file bytes to /files/upload/{ticket}. Those bytes are streamed
straight to GoFile, so multi-gigabyte files never land on the server disk.

POST /files/upload (multipart) stays for older clients.
"""

import secrets
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import _init_data_from_headers, get_storage_dep, resolve_user
from backend.database.database import get_session
from backend.database.models import User
from backend.bot.keyboards import NO_PREVIEW, file_ready_keyboard
from backend.bot import runtime
from backend.services import file_service
from backend.services.errors import AppError
from backend.services.notifier import get_notifier
from backend.services.storage_service import StorageService
from backend.texts import UPLOAD_INCOMPLETE, file_ready_text
from backend.utils.security import rate_limit_allow

router = APIRouter(tags=["upload"])

TICKET_SECONDS = 15 * 60
RATE_LIMITED = "Yuklash limiti vaqtincha to‘lgan. Keyinroq urinib ko‘ring."
TICKET_INVALID = "Yuklash muddati tugadi. Faylni qayta tanlang."


@dataclass
class _Ticket:
    user_id: int
    file_name: str
    content_type: str | None
    size: int
    expires: float


_tickets: dict[str, _Ticket] = {}


class UploadStart(BaseModel):
    file_name: str
    file_size: int
    content_type: str | None = None
    init_data: str = ""


def _measured_size(upload: UploadFile) -> int:
    stream = upload.file
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    return int(size)


async def _notify_ready(user: User, result: dict) -> None:
    if not result.get("share_url"):
        return
    await get_notifier().send_message(
        user.telegram_id,
        file_ready_text(
            result["file_name"],
            result["file_size_text"],
            result["share_url"],
            result["page_url"],
            result.get("download_url") or "",
            promo_username=runtime.bot_username or "",
        ),
        reply_markup=file_ready_keyboard(result["share_url"]),
        link_preview_options=NO_PREVIEW,
    )


@router.post("/files/upload/start")
async def start_upload(
    body: UploadStart,
    request: Request,
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
    x_telegram_init_data: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    raw = _init_data_from_headers(x_telegram_init_data, authorization) or body.init_data
    user = await resolve_user(request, session, raw)
    if not rate_limit_allow(f"upload:{user.telegram_id}", 20, 3600):
        raise AppError(429, RATE_LIMITED)
    await file_service.check_upload_allowed(session, storage, user, body.file_size)
    now = time.monotonic()
    for key in [key for key, item in _tickets.items() if item.expires <= now]:
        _tickets.pop(key, None)
    ticket = secrets.token_urlsafe(24)
    _tickets[ticket] = _Ticket(
        user_id=user.id,
        file_name=body.file_name or "file",
        content_type=body.content_type,
        size=body.file_size,
        expires=now + TICKET_SECONDS,
    )
    return {"ticket": ticket, "upload_url": f"/api/files/upload/{ticket}"}


@router.put("/files/upload/{ticket}")
async def stream_upload(
    ticket: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
    content_length: int | None = Header(default=None),
):
    item = _tickets.pop(ticket, None)
    if item is None or item.expires <= time.monotonic():
        raise AppError(410, TICKET_INVALID)
    if content_length != item.size:
        raise AppError(400, UPLOAD_INCOMPLETE)
    user = await session.get(User, item.user_id)
    if user is None:
        raise AppError(410, TICKET_INVALID)
    result = await file_service.create_streamed_upload(
        session,
        storage,
        user,
        request.stream(),
        item.file_name,
        item.content_type,
        item.size,
    )
    await _notify_ready(user, result)
    return result


@router.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    init_data: str = Form(""),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
    x_telegram_init_data: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    raw = _init_data_from_headers(x_telegram_init_data, authorization) or init_data
    user = await resolve_user(request, session, raw)
    if not rate_limit_allow(f"upload:{user.telegram_id}", 20, 3600):
        raise AppError(429, RATE_LIMITED)
    size = _measured_size(file)
    result = await file_service.create_upload(
        session,
        storage,
        user,
        file.file,
        file.filename or "file",
        file.content_type,
        size,
    )
    await _notify_ready(user, result)
    return result
