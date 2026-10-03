"""Storage safety limits and the GoFile adapter.

The application never calls a billing or upgrade endpoint.
Capacity is the configured GOFILE_MAX_STORAGE_GB, not a purchased plan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import Settings, get_settings
from backend.constants import FILE_ACTIVE, FILE_DELETED, FILE_EXPIRED
from backend.database.models import File
from backend.services.gofile_service import GoFileService, get_gofile
from backend.services.notifier import Notifier, get_notifier
from backend.texts import storage_blocked, storage_warning
from backend.utils.formatting import format_gb
from backend.utils.security import is_safe_gofile_url

logger = logging.getLogger("fazo")


@dataclass
class StorageDecision:
    allowed: bool
    reason: str | None
    usage_percent: float
    warning: bool
    blocked: bool
    used_bytes: int
    projected_bytes: int


class StorageService:
    def __init__(self, gofile: GoFileService, settings: Settings, notifier: Notifier) -> None:
        self.gofile = gofile
        self.settings = settings
        self.notifier = notifier
        self._warning_sent = False
        self._block_sent = False

    def _limit_bytes(self) -> int:
        return int(self.settings.gofile_max_storage_gb * (1024**3))

    def _max_file_bytes(self) -> int:
        return int(self.settings.gofile_max_file_size_gb * (1024**3))

    async def active_bytes(self, session: AsyncSession) -> int:
        value = await session.scalar(
            select(func.coalesce(func.sum(File.file_size), 0)).where(File.status == FILE_ACTIVE)
        )
        return int(value or 0)

    async def known_used_bytes(self, session: AsyncSession) -> tuple[int, str]:
        try:
            info = await self.gofile.get_storage_info()
        except Exception:
            logger.exception("storage stats failed")
            info = None
        if info and info.get("used_bytes") is not None:
            return int(info["used_bytes"]), "gofile"
        return await self.active_bytes(session), "database"

    def evaluate(self, size_bytes: int, used_bytes: int) -> StorageDecision:
        limit = self._limit_bytes()
        projected = used_bytes + max(0, size_bytes)
        usage_percent = 100.0 if limit <= 0 else round(projected * 100 / limit, 2)
        blocked = size_bytes > self._max_file_bytes() or usage_percent >= self.settings.gofile_storage_block_percent
        warning = usage_percent >= self.settings.gofile_storage_warning_percent
        reason = None
        if size_bytes > self._max_file_bytes():
            reason = "file_too_large"
        elif usage_percent >= self.settings.gofile_storage_block_percent:
            reason = "storage_blocked"
        return StorageDecision(
            allowed=reason is None,
            reason=reason,
            usage_percent=usage_percent,
            warning=warning,
            blocked=blocked,
            used_bytes=used_bytes,
            projected_bytes=projected,
        )

    async def check_can_upload(self, session: AsyncSession, size_bytes: int) -> StorageDecision:
        used, _source = await self.known_used_bytes(session)
        decision = self.evaluate(size_bytes, used)
        await self._notify(decision)
        return decision

    async def _notify(self, decision: StorageDecision) -> None:
        admin_id = self.settings.admin_telegram_id
        if not admin_id:
            return
        if decision.reason == "storage_blocked" and not self._block_sent:
            self._block_sent = True
            await self.notifier.send_message(admin_id, storage_blocked())
        elif decision.warning and decision.allowed and not self._warning_sent:
            self._warning_sent = True
            percent = min(100, int(decision.usage_percent))
            await self.notifier.send_message(admin_id, storage_warning(percent))

    async def upload_file(self, file_obj, filename: str, content_type: str | None = None) -> dict:
        return await self.gofile.upload_file(file_obj, filename, content_type)

    def create_download_link(self, *, download_page: str | None, parent_folder_code: str | None = None) -> str:
        return self.gofile.create_download_link(
            download_page=download_page,
            parent_folder_code=parent_folder_code,
        )

    async def get_file_info(self, content_id: str) -> dict | None:
        return await self.gofile.get_file_info(content_id)

    async def delete_file(self, content_ids: list[str]) -> bool:
        return await self.gofile.delete_contents(content_ids)

    async def delete_remote(self, file_row: File) -> bool:
        """Delete the upload's folder, then the file. False means GoFile did not confirm."""
        if file_row.storage_folder_id:
            if await self.delete_file([file_row.storage_folder_id]):
                return True
            logger.warning("gofile folder delete not confirmed file_row=%s", file_row.id)
        if file_row.storage_file_id and file_row.storage_file_id != file_row.storage_folder_id:
            if await self.delete_file([file_row.storage_file_id]):
                return True
        logger.warning("gofile delete not confirmed file_row=%s", file_row.id)
        return False

    async def resolve_links(self, file_row: File) -> dict[str, str | None]:
        browser = file_row.download_url if is_safe_gofile_url(file_row.download_url) else None
        download = browser
        info = await self.get_file_info(file_row.storage_file_id or "")
        if info:
            link = info.get("link")
            if isinstance(link, str) and is_safe_gofile_url(link):
                download = link
        return {"download_url": download, "browser_url": browser}

    async def get_storage_info(self, session: AsyncSession) -> dict:
        return await self.build_report(session)

    async def status_totals(self, session: AsyncSession) -> dict[str, dict[str, int]]:
        rows = (
            await session.execute(
                select(File.status, func.count(File.id), func.coalesce(func.sum(File.file_size), 0)).group_by(
                    File.status
                )
            )
        ).all()
        totals = {
            FILE_ACTIVE: {"count": 0, "bytes": 0},
            FILE_EXPIRED: {"count": 0, "bytes": 0},
            FILE_DELETED: {"count": 0, "bytes": 0},
        }
        for status, count, size in rows:
            totals[str(status)] = {"count": int(count), "bytes": int(size)}
        return totals

    async def build_report(self, session: AsyncSession) -> dict:
        totals = await self.status_totals(session)
        used, source = await self.known_used_bytes(session)
        if source == "database":
            used = totals[FILE_ACTIVE]["bytes"]
        limit = self._limit_bytes()
        percent = 0.0 if limit <= 0 else round(used * 100 / limit, 2)
        remaining = max(0, limit - used)
        return {
            "active_files": totals[FILE_ACTIVE]["count"],
            "active_bytes": totals[FILE_ACTIVE]["bytes"],
            "active_size_text": format_gb(totals[FILE_ACTIVE]["bytes"]),
            "tracked_used_bytes": used,
            "tracked_used_text": format_gb(used),
            "usage_source": source,
            "configured_limit_gb": self.settings.gofile_max_storage_gb,
            "configured_limit_text": f"{self.settings.gofile_max_storage_gb:.2f} GB",
            "usage_percent": percent,
            "remaining_bytes": remaining,
            "remaining_text": format_gb(remaining),
            "expired_files": totals[FILE_EXPIRED]["count"],
            "expired_bytes": totals[FILE_EXPIRED]["bytes"],
            "deleted_files": totals[FILE_DELETED]["count"],
            "deleted_bytes": totals[FILE_DELETED]["bytes"],
            "warning_percent": self.settings.gofile_storage_warning_percent,
            "block_percent": self.settings.gofile_storage_block_percent,
            "warning": percent >= self.settings.gofile_storage_warning_percent,
            "blocked": percent >= self.settings.gofile_storage_block_percent,
        }


_storage: StorageService | None = None


def get_storage() -> StorageService:
    global _storage
    if _storage is None:
        _storage = StorageService(get_gofile(), get_settings(), get_notifier())
    return _storage
