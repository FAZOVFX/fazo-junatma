"""Filename, URL, rate-limit, and log redaction helpers."""

import hashlib
import hmac
import logging
import re
import time
from urllib.parse import urlparse

_BUCKETS: dict[str, list[float]] = {}
_URL_PASSWORD = re.compile(r"(://[^:/]+:)([^@]+)@")


def sanitize_filename(name: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f]", "", base).strip().strip(".")
    if base in {"", ".", ".."}:
        return "file"
    if len(base) > 180:
        extension = ""
        if "." in base[-12:]:
            stem, extension = base.rsplit(".", 1)
            extension = "." + re.sub(r"[^A-Za-z0-9]", "", extension)[:10]
            base = stem
        else:
            extension = ""
        base = base[:180] + extension
    return base or "file"


def is_safe_gofile_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (host == "gofile.io" or host.endswith(".gofile.io"))


def webhook_secret(bot_token: str) -> str:
    digest = hashlib.sha256(f"fazo-junatma:{bot_token}".encode()).hexdigest()
    return digest[:32]


def rate_limit_allow(key: str, limit: int, window_seconds: float) -> bool:
    now = time.monotonic()
    bucket = _BUCKETS.setdefault(key, [])
    cutoff = now - window_seconds
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def reset_rate_limits() -> None:
    _BUCKETS.clear()


class RedactFilter(logging.Filter):
    """Remove secrets from log records, including exception tracebacks."""

    def __init__(self, secrets: list[str]):
        super().__init__()
        self._secrets = [item for item in secrets if item and len(item) >= 8]

    def _redact(self, text: str) -> str:
        cleaned = _URL_PASSWORD.sub(r"\1***@", text)
        for secret in self._secrets:
            if secret in cleaned:
                cleaned = cleaned.replace(secret, "***")
        return cleaned

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            record.args = tuple(
                self._redact(item) if isinstance(item, str) else item for item in record.args
            )
        if record.exc_info and record.exc_info[1] is not None:
            formatter = logging.Formatter()
            record.exc_text = self._redact(formatter.formatException(record.exc_info))
        return True


def install_log_redaction(secrets: list[str]) -> None:
    redact = RedactFilter(secrets)
    root = logging.getLogger()
    root.addFilter(redact)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "aiogram", "httpx", "httpcore"):
        logging.getLogger(name).addFilter(redact)
        logging.getLogger(name).setLevel(logging.WARNING if name.startswith("http") else logging.INFO)
    logging.getLogger("fazo").setLevel(logging.INFO)


def secrets_equal(left: str, right: str) -> bool:
    left_bytes = left.encode()
    right_bytes = right.encode()
    if len(left_bytes) != len(right_bytes):
        return False
    return hmac.compare_digest(left_bytes, right_bytes)
