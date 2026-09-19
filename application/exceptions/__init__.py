"""
Экспорт всех доменных исключений.
"""
from .domain_exceptions import (
    DomainException,
    WineNotFound,
    UserNotFound,
    UserAlreadyExists,
    AuthenticationError,
    ScanQuotaExceeded,
    CellarItemNotFound,
)

__all__ = [
    "DomainException",
    "WineNotFound",
    "UserNotFound",
    "UserAlreadyExists",
    "AuthenticationError",
    "ScanQuotaExceeded",
    "CellarItemNotFound",
]
