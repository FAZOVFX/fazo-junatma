"""File list, open, delete, and extension."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_storage_dep
from backend.database.database import get_session
from backend.database.models import User
from backend.database.schemas import DeleteManyRequest, ExtendRequest
from backend.services import file_service
from backend.services.storage_service import StorageService
from backend.services.wallet_service import extend_file, extension_quote
from backend.texts import extend_confirm
from backend.utils.formatting import format_uzs

router = APIRouter(prefix="/files", tags=["files"])


@router.get("")
async def list_files(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    items = await file_service.list_files(session, storage, user.id)
    return {"balance_uzs": user.balance_uzs, "balance_text": format_uzs(user.balance_uzs), "items": items}


@router.get("/{file_id}")
async def get_file(
    file_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    return await file_service.get_file(session, storage, user.id, file_id)


@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    confirm: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    return await file_service.delete_file(session, storage, user.id, file_id, confirm)


@router.post("/delete-multiple")
async def delete_multiple(
    body: DeleteManyRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    return await file_service.delete_many(session, storage, user.id, body.file_ids, body.confirm)


@router.post("/{file_id}/extend")
async def extend(
    file_id: int,
    body: ExtendRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not body.confirm:
        quote = await extension_quote(session, user.id, file_id)
        quote["title"] = "⏰ Faylni 1 kunga uzaytirish"
        quote["confirm_text"] = extend_confirm(quote["price_uzs"], quote["balance_uzs"])
        return quote
    return await extend_file(session, user.id, file_id, idempotency_key=body.idempotency_key)
