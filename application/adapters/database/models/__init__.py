"""
Экспорт всех моделей базы данных приложения.
"""
from .base import Base, UUIDMixin, TimestampMixin, GUID
from .wine import Wine
from .user import User
from .cellar import UserCellar
from .pairing import WineFoodPairing
from .scan_history import UserScanHistory
from .preference_history import UserPreferenceHistory
from .user_session import UserSession

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "GUID",
    "Wine",
    "User",
    "UserCellar",
    "WineFoodPairing",
    "UserScanHistory",
    "UserPreferenceHistory",
    "UserSession",
]
