"""Verify Telegram Mini App initData. The user id is taken only from this payload."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from backend.constants import INIT_DATA_MAX_AGE_SECONDS


class AuthError(Exception):
    """initData failed verification. The message is a short reason code, never a secret."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS,
    now: float | None = None,
) -> dict:
    if not init_data or not bot_token:
        raise AuthError("missing")
    try:
        pairs = parse_qsl(init_data, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise AuthError("malformed") from exc
    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise AuthError("hash")
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise AuthError("bad-hash")
    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError as exc:
        raise AuthError("auth_date") from exc
    current = time.time() if now is None else now
    if auth_date > current + 60 or current - auth_date > max_age_seconds:
        raise AuthError("expired")
    try:
        user = json.loads(data.get("user", ""))
    except json.JSONDecodeError as exc:
        raise AuthError("user") from exc
    if not isinstance(user, dict) or "id" not in user:
        raise AuthError("user")
    try:
        user["id"] = int(user["id"])
    except (TypeError, ValueError) as exc:
        raise AuthError("user") from exc
    start_param = data.get("start_param")
    if start_param:
        user["start_param"] = start_param
    return user
