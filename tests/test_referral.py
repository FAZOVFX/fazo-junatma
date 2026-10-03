from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.database.models import Referral
from backend.services.referral_service import award_referral, referral_link, referral_stats, register_user
from backend.utils.formatting import as_utc

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


async def _user(session, telegram_id, code=None):
    return await register_user(
        session,
        telegram_id=telegram_id,
        username=None,
        first_name="U",
        last_name=None,
        referral_code=code,
        now=NOW,
    )


async def test_referral_adds_one_day(database):
    session, _factory = database
    referrer, _created, _reward = await _user(session, 10)
    original = referrer.subscription_expires_at
    _new_user, created, rewarded = await _user(session, 11, referrer.referral_code)
    assert created is True
    assert rewarded.id == referrer.id
    await session.refresh(referrer)
    assert as_utc(referrer.subscription_expires_at) == as_utc(original) + timedelta(days=1)
    stats = await referral_stats(session, referrer.id)
    assert stats == {"invited_count": 1, "bonus_days": 1}


async def test_repeated_start_does_not_reward_again(database):
    session, _factory = database
    referrer, _created, _reward = await _user(session, 20)
    await _user(session, 21, referrer.referral_code)
    _again, created, rewarded = await _user(session, 21, referrer.referral_code)
    assert created is False
    assert rewarded is None
    await session.refresh(referrer)
    assert as_utc(referrer.subscription_expires_at) == NOW + timedelta(days=8)
    count = await session.scalar(select(func.count(Referral.id)))
    assert count == 1


async def test_self_referral_is_rejected(database):
    session, _factory = database
    user, _created, _reward = await _user(session, 30)
    result = await award_referral(session, user, user.referral_code, NOW)
    await session.commit()
    assert result is None
    stats = await referral_stats(session, user.id)
    assert stats["invited_count"] == 0


async def test_five_referrals_add_five_days(database):
    session, _factory = database
    referrer, _created, _reward = await _user(session, 40)
    for offset in range(5):
        await _user(session, 41 + offset, referrer.referral_code)
    await session.refresh(referrer)
    assert as_utc(referrer.subscription_expires_at) == NOW + timedelta(days=12)
    stats = await referral_stats(session, referrer.id)
    assert stats["bonus_days"] == 5


async def test_duplicate_reward_row_is_ignored(database):
    session, _factory = database
    referrer, _created, _reward = await _user(session, 50)
    new_user, _created, _reward = await _user(session, 51)
    first = await award_referral(session, new_user, referrer.referral_code, NOW)
    second = await award_referral(session, new_user, referrer.referral_code, NOW)
    await session.commit()
    assert first.id == referrer.id
    assert second is None
    await session.refresh(referrer)
    assert as_utc(referrer.subscription_expires_at) == NOW + timedelta(days=8)


def test_referral_link_shape():
    assert referral_link("FazoBot", "ab12cd34") == "https://t.me/FazoBot?start=ref_ab12cd34"
