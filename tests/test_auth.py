import time
from pathlib import Path

from backend.utils.telegram_auth import AuthError, verify_init_data
from tests.conftest import TOKEN, auth_headers, make_init_data


async def test_health(api):
    client, _storage, _factory = api
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_init_data():
    raw = make_init_data({"id": 77, "first_name": "Ali", "username": "ali"})
    user = verify_init_data(raw, TOKEN)
    assert user["id"] == 77
    assert user["username"] == "ali"


def test_bad_hash_rejected():
    raw = make_init_data({"id": 77, "first_name": "Ali"}) + "x"
    try:
        verify_init_data(raw, TOKEN)
        assert False
    except AuthError as exc:
        assert exc.reason in {"bad-hash", "malformed"}


def test_expired_init_data():
    raw = make_init_data({"id": 77, "first_name": "Ali"}, auth_date=int(time.time()) - 90000)
    try:
        verify_init_data(raw, TOKEN)
        assert False
    except AuthError as exc:
        assert exc.reason == "expired"


def test_tampered_user_rejected():
    raw = make_init_data({"id": 77, "first_name": "Ali"})
    swapped = raw.replace("77", "78", 1)
    try:
        verify_init_data(swapped, TOKEN)
        assert False
    except AuthError:
        pass


async def test_me_uses_verified_identity(api):
    client, _storage, _factory = api
    response = await client.get("/api/me", headers=auth_headers(501, first_name="Vali"))
    assert response.status_code == 200
    body = response.json()
    assert body["telegram_id"] == 501
    assert body["first_name"] == "Vali"
    assert body["subscription_status"] == "trial"
    assert body["is_admin"] is False


async def test_spoofed_query_user_is_ignored(api):
    client, _storage, _factory = api
    await client.get("/api/me", headers=auth_headers(11))
    response = await client.get("/api/me?user_id=11", headers=auth_headers(22, first_name="Bob"))
    assert response.status_code == 200
    assert response.json()["telegram_id"] == 22


async def test_missing_init_data(api):
    client, _storage, _factory = api
    response = await client.get("/api/me")
    assert response.status_code == 401


async def test_admin_gate(api):
    client, _storage, _factory = api
    denied = await client.get("/api/admin/payments", headers=auth_headers(11))
    assert denied.status_code == 403
    allowed = await client.get("/api/admin/statistics", headers=auth_headers(4242, first_name="Admin"))
    assert allowed.status_code == 200


def test_env_example_has_no_gateway_variables():
    sources = [
        Path(".env.example").read_text(encoding="utf-8").upper(),
        Path("backend/config.py").read_text(encoding="utf-8").upper(),
        Path("backend/services/payment_service.py").read_text(encoding="utf-8").upper(),
    ]
    for source in sources:
        assert "CLICK_" not in source
        assert "PAYME_" not in source
