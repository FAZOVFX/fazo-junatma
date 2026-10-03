"""API request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class MeResponse(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    balance_uzs: int
    balance_text: str
    subscription_status: str
    subscription_label: str
    remaining_text: str
    is_trial: bool
    is_admin: bool
    subscription_expires_at: datetime
    referral_code: str


class FileResponse(BaseModel):
    id: int
    file_name: str
    file_size: int
    file_size_text: str
    created_at: datetime
    expires_at: datetime
    remaining_text: str
    status: str
    status_label: str
    download_url: str | None = None
    browser_url: str | None = None


class ExtendRequest(BaseModel):
    confirm: bool = False
    idempotency_key: str | None = Field(default=None, max_length=160)


class DeleteManyRequest(BaseModel):
    file_ids: list[int] = Field(min_length=1, max_length=100)
    confirm: bool = False


class PaymentCreateRequest(BaseModel):
    type: str
    amount_uzs: int | None = None
    description: str | None = Field(default=None, max_length=500)


class WalletResponse(BaseModel):
    balance_uzs: int
    balance_text: str
    extension_price_uzs: int
    extension_price_text: str


class ReferralResponse(BaseModel):
    referral_code: str
    invited_count: int
    bonus_days: int
    reward_days_each: int
    link: str
    bot_username: str | None
