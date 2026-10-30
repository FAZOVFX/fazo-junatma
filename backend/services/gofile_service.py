"""GoFile client.

Verified against the official API reference at https://gofile.io/api on 2026-10-03.

Endpoints used:
- POST https://upload.gofile.io/uploadfile
- DELETE https://api.gofile.io/contents
- GET https://api.gofile.io/contents/{contentId}  (Premium; callers fall back to the database)
- GET https://api.gofile.io/accounts/getid
- GET https://api.gofile.io/accounts/{accountId}

Authentication is Authorization: Bearer with the account token.
The token is the account itself. It is never sent to the browser.
There is no scoped upload token in the current API, so the browser does not upload directly.

Not called, on purpose:
- billing, upgrades, or any payment endpoint
- POST /accounts/{id}/resettoken
- direct-link endpoints (Premium). Sharing uses the downloadPage URL from the upload response.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import AsyncIterator

import httpx

from backend.services.errors import GoFileError
from backend.utils.security import is_safe_gofile_url

logger = logging.getLogger("fazo")

UPLOAD_URL = "https://upload.gofile.io/uploadfile"
API_BASE = "https://api.gofile.io"
_CODE = re.compile(r"^[A-Za-z0-9]{4,32}$")
# Multi-gigabyte files: GoFile may take a long time to answer after the last byte,
# so the read wait is generous instead of the 10-minute default.
_UPLOAD_TIMEOUT = httpx.Timeout(connect=30.0, read=3600.0, write=600.0, pool=60.0)


class GoFileService:
    def __init__(
        self,
        token: str,
        account_id: str = "",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = (token or "").strip()
        self._account_id = (account_id or "").strip()
        self._http = http_client

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _owned_client(self, timeout: httpx.Timeout | None = None) -> tuple[httpx.AsyncClient, bool]:
        if self._http is not None:
            return self._http, False
        client_timeout = timeout or httpx.Timeout(600.0, connect=30.0)
        return httpx.AsyncClient(timeout=client_timeout), True

    def _payload(self, response: httpx.Response) -> dict:
        try:
            body = response.json()
        except Exception as exc:
            snippet = " ".join(response.text[:300].split())
            logger.warning("gofile non-json http=%s body=%r", response.status_code, snippet)
            raise GoFileError(f"invalid-response-http-{response.status_code}") from exc
        if not isinstance(body, dict):
            raise GoFileError("invalid-response")
        status = str(body.get("status") or f"http-{response.status_code}")
        if status != "ok":
            raise GoFileError(status)
        data = body.get("data") or {}
        if isinstance(data, dict):
            data.pop("token", None)
            return data
        return {"value": data}

    async def upload_file(self, file_obj, filename: str, content_type: str | None = None) -> dict:
        if not self._token:
            raise GoFileError("not-configured")
        client, close = await self._owned_client(_UPLOAD_TIMEOUT)
        try:
            files = {
                "file": (filename, file_obj, content_type or "application/octet-stream"),
            }
            response = await client.post(UPLOAD_URL, headers=self._headers(), files=files, timeout=_UPLOAD_TIMEOUT)
            data = self._payload(response)
        finally:
            if close:
                await client.aclose()
        return self._stored(data, filename)

    async def upload_stream(
        self,
        chunks: AsyncIterator[bytes],
        filename: str,
        content_type: str | None,
        size: int,
    ) -> dict:
        """Forward an incoming byte stream to GoFile as it arrives, without a temp file.

        Large files never touch the local disk, and GoFile receives the bytes while the
        browser is still sending them, so the link is ready right after the last chunk.
        """
        if not self._token:
            raise GoFileError("not-configured")
        boundary = secrets.token_hex(16)
        safe = filename.replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe}"\r\n'
            f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n"
        ).encode("utf-8")
        tail = f"\r\n--{boundary}--\r\n".encode()

        async def body() -> AsyncIterator[bytes]:
            yield head
            sent = 0
            async for chunk in chunks:
                if not chunk:
                    continue
                sent += len(chunk)
                if sent > size:
                    raise GoFileError("size-mismatch")
                yield chunk
            if sent != size:
                raise GoFileError("size-mismatch")
            yield tail

        headers = {
            **self._headers(),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(head) + size + len(tail)),
        }
        client, close = await self._owned_client(_UPLOAD_TIMEOUT)
        try:
            response = await client.post(UPLOAD_URL, headers=headers, content=body(), timeout=_UPLOAD_TIMEOUT)
            if response.status_code >= 400:
                logger.warning("gofile upload http=%s", response.status_code)
            data = self._payload(response)
        finally:
            if close:
                await client.aclose()
        return self._stored(data, filename)

    def _stored(self, data: dict, filename: str) -> dict:
        download_url = self.create_download_link(
            download_page=data.get("downloadPage"),
            parent_folder_code=data.get("parentFolderCode"),
            file_code=data.get("code"),
        )
        file_id = data.get("id")
        if not file_id:
            raise GoFileError("missing-file-id")
        return {
            "storage_file_id": str(file_id),
            "storage_folder_id": data.get("parentFolder"),
            "download_url": download_url,
            "file_name": data.get("name") or filename,
            "file_size": int(data.get("size") or 0),
        }

    def create_download_link(
        self,
        *,
        download_page: str | None,
        parent_folder_code: str | None = None,
        file_code: str | None = None,
    ) -> str:
        if is_safe_gofile_url(download_page):
            return str(download_page)
        for code in (parent_folder_code, file_code):
            if code and _CODE.fullmatch(str(code)):
                url = f"https://gofile.io/d/{code}"
                if is_safe_gofile_url(url):
                    return url
        raise GoFileError("invalid-download-url")

    async def get_file_info(self, content_id: str) -> dict | None:
        """Return content metadata. Premium-only on GoFile; None means use the database."""
        if not self._token or not content_id:
            return None
        client, close = await self._owned_client()
        try:
            response = await client.get(f"{API_BASE}/contents/{content_id}", headers=self._headers())
            try:
                body = response.json()
            except Exception:
                return None
        finally:
            if close:
                await client.aclose()
        if not isinstance(body, dict):
            return None
        status = body.get("status")
        if status == "error-notPremium":
            return None
        if status != "ok":
            logger.info("gofile content lookup status=%s", status)
            return None
        data = body.get("data") or {}
        if isinstance(data, dict):
            data.pop("token", None)
            return data
        return None

    async def delete_contents(self, content_ids: list[str]) -> bool:
        ids = [item for item in content_ids if item]
        if not ids or not self._token:
            return False
        client, close = await self._owned_client()
        try:
            response = await client.request(
                "DELETE",
                f"{API_BASE}/contents",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"contentsId": ",".join(ids)},
            )
            try:
                body = response.json()
            except Exception:
                logger.warning("gofile delete returned a non-json response")
                return False
        finally:
            if close:
                await client.aclose()
        status = body.get("status") if isinstance(body, dict) else None
        if status in {"ok", "error-notFound"}:
            return True
        logger.warning("gofile delete not confirmed status=%s", status)
        return False

    async def get_storage_info(self) -> dict | None:
        """Account statsCurrent.storage when the API returns it. Never returns the token."""
        if not self._token:
            return None
        client, close = await self._owned_client(httpx.Timeout(12.0, connect=5.0))
        try:
            account_id = self._account_id
            if not account_id:
                ident = await client.get(f"{API_BASE}/accounts/getid", headers=self._headers())
                ident_data = self._payload(ident)
                account_id = str(ident_data.get("id") or "")
                self._account_id = account_id
            if not account_id:
                return None
            response = await client.get(f"{API_BASE}/accounts/{account_id}", headers=self._headers())
            data = self._payload(response)
        except (GoFileError, httpx.HTTPError) as exc:
            status = getattr(exc, "status", None) or type(exc).__name__
            logger.info("gofile storage stats unavailable status=%s", status)
            return None
        finally:
            if close:
                await client.aclose()
        stats = data.get("statsCurrent") or {}
        if "storage" not in stats:
            return None
        return {
            "source": "gofile",
            "used_bytes": int(stats.get("storage") or 0),
            "file_count": stats.get("fileCount"),
            "folder_count": stats.get("folderCount"),
        }


_client: GoFileService | None = None


def get_gofile() -> GoFileService:
    global _client
    if _client is None:
        from backend.config import get_settings

        settings = get_settings()
        _client = GoFileService(settings.gofile_api_token, settings.gofile_account_id)
    return _client
