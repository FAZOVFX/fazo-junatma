"""Streaming upload. The file object is forwarded to GoFile without reading it all into memory."""

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import _init_data_from_headers, get_storage_dep, resolve_user
from backend.database.database import get_session
from backend.bot.keyboards import NO_PREVIEW, file_ready_keyboard
from backend.bot import runtime
from backend.services import file_service
from backend.services.errors import AppError
from backend.services.notifier import get_notifier
from backend.services.storage_service import StorageService
from backend.texts import file_ready_text
from backend.utils.security import rate_limit_allow

router = APIRouter(tags=["upload"])


def _measured_size(upload: UploadFile) -> int:
    stream = upload.file
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    return int(size)


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
        raise AppError(429, "Yuklash limiti vaqtincha to‘lgan. Keyinroq urinib ko‘ring.")
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
    if result.get("share_url"):
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
    return result
