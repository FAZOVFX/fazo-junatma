"""Aggregate API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api import files, payments, upload, users
from backend.api.deps import get_storage_dep, require_admin
from backend.database.database import get_session
from backend.database.models import User
from backend.services.admin_service import list_users, list_wallet_operations, statistics
from backend.services.storage_service import StorageService
from backend.utils.formatting import as_utc, format_uzs

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(upload.router)
api_router.include_router(payments.router)
api_router.include_router(files.router)


@api_router.get("/admin/storage")
async def admin_storage(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    return await storage.build_report(session)


@api_router.get("/admin/statistics")
async def admin_statistics(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    storage: StorageService = Depends(get_storage_dep),
):
    return await statistics(session, storage)


@api_router.get("/admin/users")
async def admin_users(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = await list_users(session)
    return {
        "items": [
            {
                "id": row.id,
                "telegram_id": row.telegram_id,
                "username": row.username,
                "first_name": row.first_name,
                "balance_uzs": row.balance_uzs,
                "balance_text": format_uzs(row.balance_uzs),
                "subscription_status": row.subscription_status,
                "subscription_expires_at": as_utc(row.subscription_expires_at).isoformat(),
                "created_at": as_utc(row.created_at).isoformat(),
            }
            for row in rows
        ]
    }


@api_router.get("/admin/wallet-transactions")
async def admin_wallet(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = await list_wallet_operations(session)
    return {
        "items": [
            {
                "id": row.id,
                "user_id": row.user_id,
                "type": row.type,
                "amount_uzs": row.amount_uzs,
                "amount_text": format_uzs(row.amount_uzs),
                "balance_before": row.balance_before,
                "balance_after": row.balance_after,
                "description": row.description,
                "payment_id": row.payment_id,
                "created_at": as_utc(row.created_at).isoformat(),
            }
            for row in rows
        ]
    }
