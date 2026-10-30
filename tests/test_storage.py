import io
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.services.errors import GoFileError
from backend.services.gofile_service import API_BASE, UPLOAD_URL, GoFileService
from backend.services.notifier import Notifier
from backend.services.storage_service import StorageService
from backend.utils.security import is_safe_gofile_url, sanitize_filename


def _settings(**overrides):
    values = dict(
        gofile_max_storage_gb=100,
        gofile_max_file_size_gb=10,
        gofile_storage_warning_percent=80,
        gofile_storage_block_percent=95,
        admin_telegram_id=4242,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_download_link_falls_back_to_file_code():
    service = GoFileService("token")
    url = service.create_download_link(download_page=None, file_code="Qp9w8eR7")
    assert url == "https://gofile.io/d/Qp9w8eR7"


def test_filename_strips_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert "/" not in sanitize_filename("..\\..\\secret.txt")
    assert sanitize_filename("") == "file"
    assert is_safe_gofile_url("https://gofile.io/d/abcd1234")
    assert not is_safe_gofile_url("http://evil.example/d/abcd")
    assert not is_safe_gofile_url("https://gofile.io.evil.com/d/abcd")


def test_file_size_and_capacity_limits():
    service = StorageService(SimpleNamespace(), _settings(), Notifier())
    limit = 100 * (1024**3)
    too_big = service.evaluate(11 * (1024**3), 0)
    assert too_big.allowed is False
    assert too_big.reason == "file_too_large"
    warning = service.evaluate(1, int(limit * 0.80))
    assert warning.allowed is True
    assert warning.warning is True
    blocked = service.evaluate(6 * (1024**3), int(limit * 0.90))
    assert blocked.allowed is False
    assert blocked.reason == "storage_blocked"


async def test_warning_and_block_notify_admin_once():
    class Stats:
        def __init__(self, used):
            self.used = used

        async def get_storage_info(self):
            return {"used_bytes": self.used}

    notifier = Notifier()
    limit = 100 * (1024**3)
    warning_service = StorageService(Stats(int(limit * 0.81)), _settings(), notifier)
    decision = await warning_service.check_can_upload(None, 1)
    await warning_service.check_can_upload(None, 1)
    assert decision.allowed is True
    assert len(notifier.outbox) == 1
    assert "80" in notifier.outbox[0]["text"] or "81" in notifier.outbox[0]["text"]

    blocker = Notifier()
    block_service = StorageService(Stats(int(limit * 0.96)), _settings(), blocker)
    blocked = await block_service.check_can_upload(None, 1)
    assert blocked.allowed is False
    assert blocker.outbox[0]["telegram_id"] == 4242
    assert "to" in blocker.outbox[0]["text"].lower() or "🛑" in blocker.outbox[0]["text"]


async def test_gofile_uses_documented_endpoints_and_hides_token():
    secret = "SUPERSECRETTOKENVALUE"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {secret}":
            return httpx.Response(401, json={"status": "error-token", "token": secret})
        if request.method == "POST" and str(request.url) == UPLOAD_URL:
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "id": "file-1",
                        "parentFolder": "folder-1",
                        "downloadPage": "https://gofile.io/d/abcd1234",
                        "name": "a.txt",
                        "size": 4,
                        "token": secret,
                    },
                },
            )
        if request.method == "DELETE" and str(request.url) == f"{API_BASE}/contents":
            body = json.loads(request.content.decode())
            assert body["contentsId"] == "folder-1"
            return httpx.Response(200, json={"status": "ok", "data": {}})
        if request.method == "GET" and str(request.url) == f"{API_BASE}/contents/file-1":
            return httpx.Response(200, json={"status": "error-notPremium"})
        if request.method == "GET" and str(request.url) == f"{API_BASE}/accounts/acc-1":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "id": "acc-1",
                        "token": secret,
                        "statsCurrent": {"storage": 12, "fileCount": 1, "folderCount": 1},
                    },
                },
            )
        if request.method == "POST":
            return httpx.Response(401, json={"status": "error-token", "token": secret})
        return httpx.Response(404, json={"status": "error-notFound"})

    client = GoFileService(secret, "acc-1", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    uploaded = await client.upload_file(io.BytesIO(b"data"), "a.txt", "text/plain")
    assert uploaded["download_url"] == "https://gofile.io/d/abcd1234"
    assert secret not in json.dumps(uploaded)
    assert await client.get_file_info("file-1") is None
    info = await client.get_storage_info()
    assert info["used_bytes"] == 12
    assert secret not in json.dumps(info)
    assert await client.delete_contents(["folder-1"]) is True

    failing = GoFileService("other-token", "", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(GoFileError) as caught:
        await failing.upload_file(io.BytesIO(b"x"), "b.txt")
    assert secret not in str(caught.value)


async def test_upload_stream_forwards_bytes_as_multipart():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        seen["url"] = str(request.url)
        seen["length"] = request.headers["content-length"]
        seen["type"] = request.headers["content-type"]
        seen["body"] = body
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "data": {
                    "id": "file-uuid",
                    "parentFolder": "folder-uuid",
                    "downloadPage": "https://gofile.io/d/x7k2p9Qm",
                    "name": "big.bin",
                    "size": 10,
                },
            },
        )

    async def chunks():
        yield b"01234"
        yield b"56789"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = GoFileService("token", http_client=client)
        stored = await service.upload_stream(chunks(), "big.bin", "application/octet-stream", 10)

    assert seen["url"] == UPLOAD_URL
    assert int(seen["length"]) == len(seen["body"])
    assert seen["type"].startswith("multipart/form-data; boundary=")
    assert b'name="file"; filename="big.bin"' in seen["body"]
    assert b"\r\n\r\n0123456789\r\n--" in seen["body"]
    assert stored["download_url"] == "https://gofile.io/d/x7k2p9Qm"
    assert stored["storage_file_id"] == "file-uuid"


async def test_upload_stream_rejects_short_body():
    async def handler(request: httpx.Request) -> httpx.Response:
        await request.aread()
        return httpx.Response(200, json={"status": "ok", "data": {}})

    async def chunks():
        yield b"0123"

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = GoFileService("token", http_client=client)
        with pytest.raises(GoFileError) as caught:
            await service.upload_stream(chunks(), "big.bin", None, 10)
    assert caught.value.status == "size-mismatch"
