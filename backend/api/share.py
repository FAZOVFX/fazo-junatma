"""Public file page. The share code is the secret; ownership is not required."""

import re

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.database import get_session
from backend.services import file_service
from backend.services.errors import AppError
from backend.texts import MSG_FILE_NOT_FOUND
from backend.utils.security import rate_limit_allow

router = APIRouter(tags=["share"])
_CODE = re.compile(r"^[a-f0-9]{12}$")


@router.get("/share/{code}")
async def public_file(code: str, session: AsyncSession = Depends(get_session)):
    if not _CODE.fullmatch(code):
        raise AppError(404, MSG_FILE_NOT_FOUND)
    if not rate_limit_allow(f"share:{code}", 120, 60):
        raise AppError(429, "Juda ko‘p so‘rov. Birozdan keyin urinib ko‘ring.")
    return await file_service.get_public_file(session, code)
