"""Custom exceptions for pyskmover."""


class SkMowerError(Exception):
    """Base exception for all pyskmover errors."""


class SkMowerAuthError(SkMowerError):
    """Raised when authentication fails (token request or refresh)."""


class SkMowerConnectionError(SkMowerError):
    """Raised when a network/connection error occurs."""


class SkMowerApiError(SkMowerError):
    """Raised when the server returns a non-zero code in the JSON response."""

    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"API error {code}: {msg}")