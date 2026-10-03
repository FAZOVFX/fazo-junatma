"""Wallet balance, file-extension charges, and transaction history."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.constants import EXTENSION_HOURS, EXTENSION_PRICE_UZS, WALLET_EXTENSION
from backend.database.models import File, IdempotencyKey, User, WalletTransaction
from backend.services.errors import AppError
from backend.services.locks import resource_lock
from backend.texts import MSG_FILE_EXPIRED, MSG_FILE_NOT_FOUND, insufficient_balance
from backend.utils.formatting import as_utc, format_uzs, utcnow


async def _lock_user(session: AsyncSession, user_id: int) -> User:
    stmt = select(User).where(User.id == user_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    user = await session.scalar(stmt)
    if user is None:
        raise AppError(404, "Foydalanuvchi topilmadi.")
    return user


async def _lock_file(session: AsyncSession, file_id: int) -> File | None:
    stmt = select(File).where(File.id == file_id)
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


def extension_key(file: File) -> str:
    return f"extend:{file.id}:{as_utc(file.expires_at).isoformat()}"


def _quote(user: User, file: File, now) -> dict:
    price = EXTENSION_PRICE_UZS
    short = max(0, price - user.balance_uzs)
    expires = as_utc(file.expires_at)
    return {
        "file_id": file.id,
        "price_uzs": price,
        "price_text": format_uzs(price),
        "balance_uzs": user.balance_uzs,
        "balance_text": format_uzs(user.balance_uzs),
        "enough": user.balance_uzs >= price,
        "short_uzs": short,
        "short_text": format_uzs(short),
        "expires_at": expires.isoformat(),
        "preview_expires_at": (expires + timedelta(hours=EXTENSION_HOURS)).isoformat(),
        "idempotency_key": extension_key(file),
        "message": insufficient_balance(user.balance_uzs, price, short) if short else None,
    }


async def extension_quote(session: AsyncSession, user_id: int, file_id: int, now=None) -> dict:
    now = now or utcnow()
    user = await session.get(User, user_id)
    file = await session.get(File, file_id)
    if user is None or file is None or file.user_id != user.id or file.status == "deleted":
        raise AppError(404, MSG_FILE_NOT_FOUND)
    if file.status != "active" or as_utc(file.expires_at) <= now:
        raise AppError(409, MSG_FILE_EXPIRED)
    return _quote(user, file, now)


async def extend_file(
    session: AsyncSession,
    user_id: int,
    file_id: int,
    now=None,
    idempotency_key: str | None = None,
) -> dict:
    now = now or utcnow()
    async with resource_lock("wallet", user_id):
        user = await _lock_user(session, user_id)
        file = await _lock_file(session, file_id)
        if file is None or file.user_id != user.id or file.status == "deleted":
            raise AppError(404, MSG_FILE_NOT_FOUND)
        if file.status != "active" or as_utc(file.expires_at) <= now:
            raise AppError(409, MSG_FILE_EXPIRED)

        canonical = extension_key(file)
        key = (idempotency_key or canonical)[:160]
        if not key.startswith(f"extend:{file.id}:"):
            raise AppError(422, "So‘rov yaroqsiz.")
        existing = await session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user.id,
                IdempotencyKey.scope == "file_extension",
                IdempotencyKey.key == key,
            )
        )
        if existing and existing.response_json:
            replay = dict(existing.response_json)
            replay["replayed"] = True
            return replay
        if key != canonical:
            raise AppError(409, "Uzaytirish holati eskirgan. Qayta urinib ko‘ring.")

        price = EXTENSION_PRICE_UZS
        if user.balance_uzs < price:
            short = price - user.balance_uzs
            raise AppError(
                402,
                insufficient_balance(user.balance_uzs, price, short),
                {
                    "balance_uzs": user.balance_uzs,
                    "balance_text": format_uzs(user.balance_uzs),
                    "required_uzs": price,
                    "required_text": format_uzs(price),
                    "short_uzs": short,
                    "short_text": format_uzs(short),
                },
            )

        before = user.balance_uzs
        user.balance_uzs = before - price
        if user.balance_uzs < 0:
            raise AppError(402, insufficient_balance(before, price, price - before))
        file.expires_at = as_utc(file.expires_at) + timedelta(hours=EXTENSION_HOURS)
        user.updated_at = now
        session.add(
            WalletTransaction(
                user_id=user.id,
                type=WALLET_EXTENSION,
                amount_uzs=-price,
                balance_before=before,
                balance_after=user.balance_uzs,
                description="Faylni 24 soatga uzaytirish",
                payment_id=None,
                created_at=now,
            )
        )
        response = {
            "file_id": file.id,
            "balance_uzs": user.balance_uzs,
            "balance_text": format_uzs(user.balance_uzs),
            "charged_uzs": price,
            "expires_at": file.expires_at.isoformat(),
            "replayed": False,
        }
        session.add(
            IdempotencyKey(
                key=key,
                user_id=user.id,
                scope="file_extension",
                response_json=response,
                created_at=now,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == user_id,
                    IdempotencyKey.scope == "file_extension",
                    IdempotencyKey.key == key,
                )
            )
            if existing and existing.response_json:
                replay = dict(existing.response_json)
                replay["replayed"] = True
                return replay
            raise
        return response


async def list_transactions(session: AsyncSession, user_id: int, limit: int = 30) -> list[WalletTransaction]:
    rows = await session.scalars(
        select(WalletTransaction)
        .where(WalletTransaction.user_id == user_id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(limit)
    )
    return list(rows)
