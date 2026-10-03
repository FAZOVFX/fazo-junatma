"""Streaming upload. The file object is forwarded to GoFile without reading it all into memory."""

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_storage_dep
from backend.database.database import get_session
from backend.database.models import User
from backend.services import file_service
from backend.services.errors import AppError
from backend.services.storage_service import StorageService
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
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    if not rate_limit_allow(f"upload:{user.telegram_id}", 20, 3600):
        raise AppError(429, "Yuklash limiti vaqtincha to‘lgan. Keyinroq urinib ko‘ring.")
    size = _measured_size(file)
    return await file_service.create_upload(
        session,
        storage,
        user,
        file.file,
        file.filename or "file",
        file.content_type,
        size,
    )
