"""File ownership, lifetime, deletion, and upload records."""

import logging
from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import FILE_ACTIVE, FILE_DELETED, FILE_EXPIRED, FILE_LIFETIME_HOURS
from backend.database.models import File, User
from backend.services.errors import AppError, GoFileError
from backend.services.storage_service import StorageService
from backend.services.subscription_service import subscription_is_valid, sync_subscription_status
from backend.texts import (
    CONFIRM_REQUIRED,
    MSG_FILE_EXPIRED,
    MSG_FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    GOFILE_NOT_CONFIGURED,
    SUBSCRIPTION_REQUIRED,
    UPLOAD_ERROR,
    UPLOAD_STOPPED,
)
from backend.utils.formatting import as_utc, file_status_label, format_duration, format_size, utcnow
from backend.utils.security import is_safe_gofile_url, sanitize_filename

logger = logging.getLogger("fazo")


def serialize_file(row: File, now, links: dict | None = None) -> dict:
    remaining = as_utc(row.expires_at) - now
    active = row.status == FILE_ACTIVE and remaining.total_seconds() > 0
    payload = {
        "id": row.id,
        "file_name": row.file_name,
        "file_size": row.file_size,
        "file_size_text": format_size(row.file_size),
        "created_at": as_utc(row.created_at).isoformat(),
        "expires_at": as_utc(row.expires_at).isoformat(),
        "remaining_text": format_duration(remaining) if active else "0 daqiqa",
        "status": row.status if not (row.status == FILE_ACTIVE and not active) else FILE_EXPIRED,
        "status_label": file_status_label(row.status if active or row.status != FILE_ACTIVE else FILE_EXPIRED),
        "download_url": None,
        "browser_url": None,
    }
    if active and links:
        payload["download_url"] = links.get("download_url")
        payload["browser_url"] = links.get("browser_url")
    elif active and is_safe_gofile_url(row.download_url):
        payload["download_url"] = row.download_url
        payload["browser_url"] = row.download_url
    return payload


async def _owned_or_404(session: AsyncSession, user_id: int, file_id: int) -> File:
    row = await session.get(File, file_id)
    if row is None or row.user_id != user_id or row.status == FILE_DELETED:
        raise AppError(404, MSG_FILE_NOT_FOUND)
    return row


async def list_files(session: AsyncSession, storage: StorageService, user_id: int, now=None) -> list[dict]:
    now = now or utcnow()
    rows = (
        await session.scalars(
            select(File)
            .where(File.user_id == user_id, File.status != FILE_DELETED)
            .order_by(File.created_at.desc())
        )
    ).all()
    items = []
    changed = False
    for row in rows:
        if row.status == FILE_ACTIVE and as_utc(row.expires_at) <= now:
            await storage.delete_remote(row)
            row.status = FILE_EXPIRED
            changed = True
        items.append(serialize_file(row, now))
    if changed:
        await session.commit()
    return items


async def get_file(session: AsyncSession, storage: StorageService, user_id: int, file_id: int, now=None) -> dict:
    now = now or utcnow()
    row = await _owned_or_404(session, user_id, file_id)
    if row.status == FILE_ACTIVE and as_utc(row.expires_at) <= now:
        remote = await storage.delete_remote(row)
        row.status = FILE_EXPIRED
        await session.commit()
        raise AppError(410, MSG_FILE_EXPIRED, {"remote_deleted": remote})
    if row.status != FILE_ACTIVE:
        raise AppError(410, MSG_FILE_EXPIRED)
    links = await storage.resolve_links(row)
    return serialize_file(row, now, links)


async def create_upload(
    session: AsyncSession,
    storage: StorageService,
    user: User,
    file_obj,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    now=None,
) -> dict:
    now = now or utcnow()
    sync_subscription_status(user, now)
    if not subscription_is_valid(user, now):
        await session.commit()
        raise AppError(403, SUBSCRIPTION_REQUIRED)
    safe_name = sanitize_filename(filename)
    if size_bytes <= 0:
        raise AppError(422, "Bo‘sh fayl yuborildi.")
    decision = await storage.check_can_upload(session, size_bytes)
    if not decision.allowed:
        if decision.reason == "file_too_large":
            raise AppError(413, FILE_TOO_LARGE)
        raise AppError(409, UPLOAD_STOPPED)
    try:
        stored = await storage.upload_file(file_obj, safe_name, content_type)
    except GoFileError as exc:
        logger.info("upload failed user=%s status=%s", user.telegram_id, exc.status)
        if exc.status == "not-configured":
            raise AppError(503, GOFILE_NOT_CONFIGURED) from exc
        raise AppError(502, UPLOAD_ERROR) from exc
    except Exception as exc:
        logger.exception("upload failed user=%s", user.telegram_id)
        raise AppError(502, UPLOAD_ERROR) from exc

    download_url = stored.get("download_url")
    if not is_safe_gofile_url(download_url):
        logger.error("rejected unsafe download url user=%s", user.telegram_id)
        await storage.delete_remote(
            SimpleNamespace(
                id=0,
                storage_folder_id=stored.get("storage_folder_id"),
                storage_file_id=stored.get("storage_file_id"),
            )
        )
        raise AppError(502, UPLOAD_ERROR)

    record = File(
        user_id=user.id,
        storage_provider="gofile",
        storage_file_id=stored.get("storage_file_id"),
        storage_folder_id=stored.get("storage_folder_id"),
        file_name=safe_name,
        file_size=size_bytes,
        download_url=download_url,
        created_at=now,
        expires_at=now + timedelta(hours=FILE_LIFETIME_HOURS),
        status=FILE_ACTIVE,
        deleted_at=None,
    )
    session.add(record)
    try:
        await session.commit()
        await session.refresh(record)
    except Exception:
        await session.rollback()
        await storage.delete_remote(record)
        raise
    logger.info("file stored id=%s user=%s", record.id, user.telegram_id)
    return serialize_file(record, now, {"download_url": download_url, "browser_url": download_url})


async def delete_file(session: AsyncSession, storage: StorageService, user_id: int, file_id: int, confirm: bool, now=None) -> dict:
    now = now or utcnow()
    if not confirm:
        raise AppError(400, CONFIRM_REQUIRED)
    row = await _owned_or_404(session, user_id, file_id)
    if row.status == FILE_DELETED:
        return {"id": row.id, "status": FILE_DELETED, "remote_deleted": False, "already": True}
    remote = await storage.delete_remote(row)
    row.status = FILE_DELETED
    row.deleted_at = now
    await session.commit()
    logger.info("file deleted id=%s user=%s remote=%s", row.id, user_id, remote)
    return {
        "id": row.id,
        "status": FILE_DELETED,
        "remote_deleted": remote,
        "message": "Fayl o‘chirildi." if remote else "Fayl tizimda yopildi. GoFile tomonda o‘chirish tasdiqlanmadi.",
    }


async def delete_many(
    session: AsyncSession,
    storage: StorageService,
    user_id: int,
    file_ids: list[int],
    confirm: bool,
    now=None,
) -> dict:
    now = now or utcnow()
    if not confirm:
        raise AppError(400, CONFIRM_REQUIRED)
    deleted = []
    denied = []
    seen: set[int] = set()
    for file_id in file_ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        row = await session.get(File, file_id)
        if row is None or row.user_id != user_id:
            denied.append(file_id)
            continue
        if row.status == FILE_DELETED:
            deleted.append({"id": row.id, "remote_deleted": False, "already": True})
            continue
        remote = await storage.delete_remote(row)
        row.status = FILE_DELETED
        row.deleted_at = now
        deleted.append({"id": row.id, "remote_deleted": remote, "already": False})
    await session.commit()
    logger.info("files deleted user=%s count=%s denied=%s", user_id, len(deleted), len(denied))
    return {"deleted": deleted, "denied": denied}


async def expire_due_files(session: AsyncSession, storage: StorageService, now=None) -> int:
    now = now or utcnow()
    rows = (
        await session.scalars(select(File).where(File.status == FILE_ACTIVE, File.expires_at <= now))
    ).all()
    for row in rows:
        remote = await storage.delete_remote(row)
        row.status = FILE_EXPIRED
        logger.info("file expired id=%s remote=%s", row.id, remote)
    if rows:
        await session.commit()
    return len(rows)
