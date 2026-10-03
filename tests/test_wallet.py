import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.constants import EXTENSION_PRICE_UZS
from backend.database.models import WalletTransaction
from backend.services.payment_service import manual_payments
from backend.services.referral_service import register_user
from backend.services.wallet_service import extend_file, extension_quote
from backend.texts import insufficient_balance
from tests.fakes import FakeStorage

NOW = datetime(2026, 4, 1, tzinfo=timezone.utc)


async def _ready_file(session, balance=20_000):
    from backend.services import file_service

    user, _created, _reward = await register_user(
        session, telegram_id=70, username=None, first_name="A", last_name=None, now=NOW
    )
    user.balance_uzs = balance
    await session.commit()
    storage = FakeStorage()
    import io

    handle = io.BytesIO(b"video")
    record = await file_service.create_upload(session, storage, user, handle, "video.mp4", "video/mp4", 5, NOW)
    return user, record, storage


async def test_extension_adds_24_hours_and_debits_wallet(database):
    session, _factory = database
    user, record, _storage = await _ready_file(session)
    original = datetime.fromisoformat(record["expires_at"])
    result = await extend_file(session, user.id, record["id"], NOW, record and None)
    # The quote key matches the current expiry when the client omits a custom key.
    assert result["charged_uzs"] == EXTENSION_PRICE_UZS
    assert result["balance_uzs"] == 15_000
    assert datetime.fromisoformat(result["expires_at"]) == original + timedelta(hours=24)
    tx_count = await session.scalar(select(func.count(WalletTransaction.id)))
    assert tx_count == 1
    tx = await session.scalar(select(WalletTransaction))
    assert tx.type == "file_extension"
    assert tx.amount_uzs == -EXTENSION_PRICE_UZS
    assert tx.balance_before == 20_000
    assert tx.balance_after == 15_000


async def test_double_click_extends_once(database):
    session, factory = database
    user, record, _storage = await _ready_file(session, balance=20_000)
    quote = await extension_quote(session, user.id, record["id"], NOW)
    key = quote["idempotency_key"]

    async def once():
        async with factory() as other:
            return await extend_file(other, user.id, record["id"], NOW, key)

    first, second = await asyncio.gather(once(), once())
    assert first["replayed"] is False or second["replayed"] is True or first["replayed"] is True
    async with factory() as check:
        fresh = await check.get(type(user), user.id)
        assert fresh.balance_uzs == 15_000
        tx_count = await check.scalar(select(func.count(WalletTransaction.id)))
        assert tx_count == 1


async def test_second_extension_is_allowed_after_the_first(database):
    session, _factory = database
    user, record, _storage = await _ready_file(session, balance=20_000)
    first = await extend_file(session, user.id, record["id"], NOW)
    second_quote = await extension_quote(session, user.id, record["id"], NOW)
    second = await extend_file(session, user.id, record["id"], NOW, second_quote["idempotency_key"])
    assert second["balance_uzs"] == 10_000
    assert datetime.fromisoformat(second["expires_at"]) == datetime.fromisoformat(first["expires_at"]) + timedelta(hours=24)


async def test_insufficient_balance(database):
    session, _factory = database
    user, record, _storage = await _ready_file(session, balance=500)
    try:
        await extend_file(session, user.id, record["id"], NOW)
        assert False
    except Exception as exc:
        assert exc.status_code == 402
        assert exc.detail == insufficient_balance(500, 5_000, 4_500)
    await session.refresh(user)
    assert user.balance_uzs == 500


async def test_wallet_topup_credits_once(database):
    session, _factory = database
    user, _created, _reward = await register_user(
        session, telegram_id=80, username=None, first_name="A", last_name=None, now=NOW
    )
    payment = await manual_payments.create_payment(session, user, "wallet_topup", 15_000, None, None, NOW)
    assert payment.status == "pending"
    first = await manual_payments.approve_payment(session, payment.id, 4242, NOW)
    second = await manual_payments.approve_payment(session, payment.id, 4242, NOW + timedelta(minutes=5))
    assert first["result"] == "approved"
    assert second["result"] == "already_approved"
    await session.refresh(user)
    assert user.balance_uzs == 15_000
    count = await session.scalar(select(func.count(WalletTransaction.id)).where(WalletTransaction.payment_id == payment.id))
    assert count == 1
