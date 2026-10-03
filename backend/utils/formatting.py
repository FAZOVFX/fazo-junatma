"""Display formatting for money, file size, and remaining time."""

from datetime import datetime, timedelta, timezone


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def format_uzs(amount: int) -> str:
    sign = "-" if int(amount) < 0 else ""
    grouped = f"{abs(int(amount)):,}".replace(",", " ")
    return f"{sign}{grouped} so\u2018m"


def format_size(num_bytes: int) -> str:
    size = max(0, int(num_bytes))
    gib = 1024**3
    mib = 1024**2
    kib = 1024
    if size >= gib:
        return f"{size / gib:.2f} GB"
    if size >= mib:
        return f"{size / mib:.2f} MB"
    if size >= kib:
        return f"{size / kib:.2f} KB"
    return f"{size} B"


def format_gb(num_bytes: int) -> str:
    return f"{max(0, int(num_bytes)) / (1024 ** 3):.2f} GB"


def format_duration(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "0 daqiqa"
    minutes_total = seconds // 60
    days, remainder = divmod(minutes_total, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days} kun")
    if hours:
        parts.append(f"{hours} soat")
    if minutes or not parts:
        parts.append(f"{minutes} daqiqa")
    return " ".join(parts)


def status_label(status: str) -> str:
    return {"trial": "Trial", "active": "Faol", "expired": "Tugagan"}.get(status, status)


def file_status_label(status: str) -> str:
    return {
        "active": "Faol",
        "expired": "Muddati tugagan",
        "deleted": "O\u2018chirilgan",
    }.get(status, status)
