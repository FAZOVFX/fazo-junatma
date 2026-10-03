import io
from datetime import datetime, timedelta, timezone

from backend.database.models import File
from backend.services import file_service
from backend.services.referral_service import register_user
from tests.conftest import auth_headers
from tests.fakes import FakeStorage

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


async def test_upload_lifetime_and_sanitized_name(api):
    client, storage, _factory = api
    response = await client.post(
        "/api/files/upload",
        headers=auth_headers(101),
        files={"file": ("../../secret.mp4", b"12345", "video/mp4")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["file_name"] == "secret.mp4"
    assert body["status"] == "active"
    created = datetime.fromisoformat(body["created_at"])
    expires = datetime.fromisoformat(body["expires_at"])
    assert expires - created == timedelta(hours=24)
    assert storage.uploaded == ["secret.mp4"]
    assert body["download_url"].startswith("https://gofile.io/")


async def test_file_ownership_and_open(api):
    client, _storage, _factory = api
    uploaded = await client.post(
        "/api/files/upload",
        headers=auth_headers(201),
        files={"file": ("video.mp4", b"abc", "video/mp4")},
    )
    file_id = uploaded.json()["id"]
    owner = await client.get(f"/api/files/{file_id}", headers=auth_headers(201))
    assert owner.status_code == 200
    assert owner.json()["download_url"].startswith("https://gofile.io/")
    stranger = await client.get(f"/api/files/{file_id}?user_id=201", headers=auth_headers(202))
    assert stranger.status_code == 404
    listing = await client.get("/api/files?user_id=201", headers=auth_headers(202))
    assert listing.status_code == 200
    assert listing.json()["items"] == []


async def test_delete_requires_confirmation_and_ownership(api):
    client, storage, _factory = api
    uploaded = await client.post(
        "/api/files/upload",
        headers=auth_headers(301),
        files={"file": ("a.bin", b"xyz", "application/octet-stream")},
    )
    file_id = uploaded.json()["id"]
    blocked = await client.delete(f"/api/files/{file_id}", headers=auth_headers(301))
    assert blocked.status_code == 400
    assert storage.deleted == []
    denied = await client.delete(f"/api/files/{file_id}?confirm=true", headers=auth_headers(302))
    assert denied.status_code == 404
    removed = await client.delete(f"/api/files/{file_id}?confirm=true", headers=auth_headers(301))
    assert removed.status_code == 200
    assert removed.json()["remote_deleted"] is True
    assert storage.deleted
    missing = await client.get(f"/api/files/{file_id}", headers=auth_headers(301))
    assert missing.status_code == 404


async def test_delete_many_only_owned_files(api):
    client, storage, _factory = api
    first = await client.post(
        "/api/files/upload", headers=auth_headers(401), files={"file": ("a.txt", b"a", "text/plain")}
    )
    second = await client.post(
        "/api/files/upload", headers=auth_headers(401), files={"file": ("b.txt", b"b", "text/plain")}
    )
    other = await client.post(
        "/api/files/upload", headers=auth_headers(402), files={"file": ("c.txt", b"c", "text/plain")}
    )
    unconfirmed = await client.post(
        "/api/files/delete-multiple",
        headers=auth_headers(401),
        json={"file_ids": [first.json()["id"]], "confirm": False},
    )
    assert unconfirmed.status_code == 400
    response = await client.post(
        "/api/files/delete-multiple",
        headers=auth_headers(401),
        json={"file_ids": [first.json()["id"], second.json()["id"], other.json()["id"]], "confirm": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert other.json()["id"] in body["denied"]
    still = await client.get(f"/api/files/{other.json()['id']}", headers=auth_headers(402))
    assert still.status_code == 200
    assert storage.fail_delete is False


async def test_remote_delete_failure_is_not_claimed(api):
    client, storage, _factory = api
    storage.fail_delete = True
    uploaded = await client.post(
        "/api/files/upload", headers=auth_headers(501), files={"file": ("a.txt", b"a", "text/plain")}
    )
    response = await client.delete(
        f"/api/files/{uploaded.json()['id']}?confirm=true",
        headers=auth_headers(501),
    )
    assert response.status_code == 200
    assert response.json()["remote_deleted"] is False
    assert "tasdiqlanmadi" in response.json()["message"]


async def test_expiration_closes_the_file(database):
    session, _factory = database
    user, _created, _reward = await register_user(
        session, telegram_id=601, username=None, first_name="A", last_name=None, now=NOW
    )
    storage = FakeStorage()
    created = await file_service.create_upload(
        session, storage, user, io.BytesIO(b"abc"), "clip.mp4", "video/mp4", 3, NOW
    )
    row = await session.get(File, created["id"])
    row.expires_at = NOW - timedelta(minutes=1)
    await session.commit()
    count = await file_service.expire_due_files(session, storage, NOW)
    assert count == 1
    await session.refresh(row)
    assert row.status == "expired"
    try:
        await file_service.get_file(session, storage, user.id, row.id, NOW)
        assert False
    except Exception as exc:
        assert exc.status_code == 410
