from datetime import datetime, timedelta, timezone

from backend.services.payment_service import manual_payments
from backend.utils.formatting import as_utc
from backend.services.referral_service import register_user
from backend.texts import RECEIPT_ACCEPTED, payment_rejected, premium_approved
from tests.conftest import auth_headers

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


async def test_screenshot_payment_stays_pending_past_thirty_minutes(database):
    session, _factory = database
    user, _created, _reward = await register_user(
        session, telegram_id=701, username=None, first_name="A", last_name=None, now=NOW
    )
    payment = await manual_payments.create_payment(session, user, "wallet_topup", 5_000, None, None, NOW)
    payment, attached = await manual_payments.attach_screenshot(session, user, "tg-file-1", payment.id, NOW)
    assert attached is True
    assert payment.status == "pending"
    later = await manual_payments.approve_payment(session, payment.id, 4242, NOW + timedelta(hours=5))
    assert later["result"] == "approved"
    assert RECEIPT_ACCEPTED.startswith("📥")


async def test_reject_does_not_change_balance_or_subscription(database):
    session, _factory = database
    user, _created, _reward = await register_user(
        session, telegram_id=702, username=None, first_name="A", last_name=None, now=NOW
    )
    expires = user.subscription_expires_at
    payment = await manual_payments.create_payment(session, user, "premium", 15_000, None, None, NOW)
    result = await manual_payments.reject_payment(session, payment.id, 4242, NOW)
    assert result["result"] == "rejected"
    await session.refresh(user)
    assert user.balance_uzs == 0
    assert as_utc(user.subscription_expires_at) == as_utc(expires)
    assert user.subscription_status == "trial"
    assert "rad etildi" in payment_rejected()


async def test_api_premium_approval(api):
    client, _storage, _factory = api
    created = await client.post("/api/payments", headers=auth_headers(801), json={"type": "premium", "amount_uzs": 1})
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "pending"
    assert body["amount_uzs"] == 15_000
    denied = await client.post(f"/api/admin/payments/{body['id']}/approve", headers=auth_headers(801))
    assert denied.status_code == 403
    approved = await client.post(f"/api/admin/payments/{body['id']}/approve", headers=auth_headers(4242))
    assert approved.status_code == 200
    assert approved.json()["result"] == "approved"
    again = await client.post(f"/api/admin/payments/{body['id']}/approve", headers=auth_headers(4242))
    assert again.json()["result"] == "already_approved"
    me = await client.get("/api/me", headers=auth_headers(801))
    assert me.json()["subscription_status"] == "active"
    assert "30 kun" in premium_approved()


async def test_api_reject(api):
    client, _storage, _factory = api
    created = await client.post(
        "/api/payments",
        headers=auth_headers(802),
        json={"type": "wallet_topup", "amount_uzs": 10000},
    )
    payment_id = created.json()["id"]
    rejected = await client.post(f"/api/admin/payments/{payment_id}/reject", headers=auth_headers(4242))
    assert rejected.status_code == 200
    assert rejected.json()["result"] == "rejected"
    wallet = await client.get("/api/wallet", headers=auth_headers(802))
    assert wallet.json()["balance_uzs"] == 0
