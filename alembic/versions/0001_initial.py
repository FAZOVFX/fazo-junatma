"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("referral_code", sa.String(length=32), nullable=False),
        sa.Column("referred_by", sa.Integer(), nullable=True),
        sa.Column("balance_uzs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subscription_status", sa.String(length=20), nullable=False),
        sa.Column("subscription_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance_uzs >= 0", name="ck_users_balance_nonnegative"),
        sa.ForeignKeyConstraint(["referred_by"], ["users.id"]),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("referral_code"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=32), nullable=False),
        sa.Column("storage_file_id", sa.String(length=64), nullable=True),
        sa.Column("storage_folder_id", sa.String(length=64), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_files_user_id", "files", ["user_id"])
    op.create_index("ix_files_user_status", "files", ["user_id", "status"])
    op.create_index("ix_files_status_expires", "files", ["status", "expires_at"])
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("amount_uzs", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("screenshot_file_id", sa.String(length=256), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.BigInteger(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.CheckConstraint("amount_uzs > 0", name="ck_payments_amount_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_user_status", "payments", ["user_id", "status"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("amount_uzs", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
    )
    op.create_index("ix_wallet_transactions_user_id", "wallet_transactions", ["user_id"])
    op.create_index("ix_wallet_user_created", "wallet_transactions", ["user_id", "created_at"])
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("referrer_user_id", sa.Integer(), nullable=False),
        sa.Column("referred_user_id", sa.Integer(), nullable=False),
        sa.Column("reward_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"]),
        sa.UniqueConstraint("referred_user_id", name="uq_referrals_referred_user"),
    )
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"])
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_user_scope_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("referrals")
    op.drop_table("wallet_transactions")
    op.drop_table("payments")
    op.drop_table("files")
    op.drop_table("users")
