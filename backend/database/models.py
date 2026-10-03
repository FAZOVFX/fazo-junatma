"""SQLAlchemy models."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("balance_uzs >= 0", name="ck_users_balance_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    balance_uzs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, default="trial")
    subscription_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subscription_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_user_status", "user_id", "status"),
        Index("ix_files_status_expires", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    storage_provider: Mapped[str] = mapped_column(String(32), nullable=False, default="gofile")
    storage_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_folder_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_user_status", "user_id", "status"),
        Index("ix_payments_status", "status"),
        CheckConstraint("amount_uzs > 0", name="ck_payments_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    screenshot_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payment_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (Index("ix_wallet_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_uzs: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_before: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referred_user_id", name="uq_referrals_referred_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    referred_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reward_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyKey(Base):
    """Prevents a repeated extend click from charging the wallet twice."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
