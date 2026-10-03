"""Domain errors mapped to API responses by the application."""


class AppError(Exception):
    def __init__(self, status_code: int, detail: str, extra: dict | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.extra = extra or {}


class GoFileError(Exception):
    def __init__(self, status: str):
        self.status = str(status)[:80]
        super().__init__(self.status)
