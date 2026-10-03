from datetime import datetime, timedelta, timezone

from backend.constants import PREMIUM_DAYS, PREMIUM_PRICE_UZS, TRIAL_DAYS
from backend.services.payment_service import manual_payments
from backend.services.referral_service import register_user
from backend.services.subscription_service import apply_premium, sync_subscription_status
from backend.utils.formatting import as_utc

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def test_new_user_gets_seven_day_trial(database):
    session, _factory = database
    user, created, _referrer = await register_user(
        session,
        telegram_id=1,
        username="ali",
        first_name="Ali",
        last_name=None,
        now=NOW,
    )
    assert created is True
    assert user.subscription_status == "trial"
    assert user.subscription_expires_at - user.subscription_started_at == timedelta(days=TRIAL_DAYS)


async def test_trial_is_granted_only_once(database):
    session, _factory = database
    first, created, _referrer = await register_user(
        session, telegram_id=2, username=None, first_name="A", last_name=None, now=NOW
    )
    later = NOW + timedelta(days=3)
    second, created_again, _referrer = await register_user(
        session, telegram_id=2, username="a", first_name="A", last_name=None, now=later
    )
    assert created is True
    assert created_again is False
    assert second.id == first.id
    assert second.subscription_expires_at == first.subscription_expires_at


async def test_premium_extends_remaining_time(database):
    session, _factory = database
    user, _created, _referrer = await register_user(
        session, telegram_id=3, username=None, first_name="A", last_name=None, now=NOW
    )
    user.subscription_expires_at = NOW + timedelta(days=5)
    user.subscription_status = "trial"
    await session.commit()
    payment = await manual_payments.create_payment(session, user, "premium", 1, None, None, NOW)
    assert payment.amount_uzs == PREMIUM_PRICE_UZS
    assert payment.status == "pending"
    result = await manual_payments.approve_payment(session, payment.id, 4242, NOW)
    assert result["result"] == "approved"
    await session.refresh(user)
    assert user.subscription_status == "active"
    assert as_utc(user.subscription_expires_at) == NOW + timedelta(days=5 + PREMIUM_DAYS)


async def test_premium_starts_from_now_when_expired(database):
    session, _factory = database
    user, _created, _referrer = await register_user(
        session, telegram_id=4, username=None, first_name="A", last_name=None, now=NOW
    )
    user.subscription_expires_at = NOW - timedelta(days=2)
    user.subscription_status = "expired"
    await session.commit()
    apply_premium(user, NOW)
    assert user.subscription_status == "active"
    assert user.subscription_expires_at == NOW + timedelta(days=PREMIUM_DAYS)


async def test_status_becomes_expired(database):
    session, _factory = database
    user, _created, _referrer = await register_user(
        session, telegram_id=5, username=None, first_name="A", last_name=None, now=NOW
    )
    changed = sync_subscription_status(user, NOW + timedelta(days=8))
    assert changed is True
    assert user.subscription_status == "expired"
