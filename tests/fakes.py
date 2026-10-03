"""In-memory storage double for API tests."""

from backend.services.storage_service import StorageDecision


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.deleted: list[str] = []
        self.fail_delete = False
        self.block = False

    async def check_can_upload(self, session, size_bytes: int) -> StorageDecision:
        if self.block:
            return StorageDecision(False, "storage_blocked", 96, True, True, 0, size_bytes)
        return StorageDecision(True, None, 10, False, False, 0, size_bytes)

    async def upload_file(self, file_obj, filename: str, content_type: str | None = None) -> dict:
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(0)
        self.uploaded.append(filename)
        return {
            "storage_file_id": f"file-{filename}",
            "storage_folder_id": f"folder-{filename}",
            "download_url": "https://gofile.io/d/abcd1234",
            "file_name": filename,
            "file_size": size,
        }

    async def delete_remote(self, file_row) -> bool:
        if self.fail_delete:
            return False
        self.deleted.append(file_row.storage_file_id)
        return True

    async def resolve_links(self, file_row) -> dict:
        return {"download_url": file_row.download_url, "browser_url": file_row.download_url}

    async def build_report(self, session) -> dict:
        return {
            "active_files": 0,
            "active_bytes": 0,
            "active_size_text": "0.00 GB",
            "tracked_used_bytes": 0,
            "tracked_used_text": "0.00 GB",
            "usage_source": "database",
            "configured_limit_gb": 100,
            "configured_limit_text": "100.00 GB",
            "usage_percent": 0,
            "remaining_bytes": 0,
            "remaining_text": "0.00 GB",
            "expired_files": 0,
            "expired_bytes": 0,
            "deleted_files": 0,
            "deleted_bytes": 0,
            "warning_percent": 80,
            "block_percent": 95,
            "warning": False,
            "blocked": False,
        }
