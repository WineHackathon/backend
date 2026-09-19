"""
Экспорт всех репозиториев слоя базы данных.
"""
from .wine_repo import WineRepository
from .user_repo import UserRepository
from .cellar_repo import CellarRepository
from .scan_repo import ScanRepository
from .preference_repo import PreferenceRepository

__all__ = [
    "WineRepository",
    "UserRepository",
    "CellarRepository",
    "ScanRepository",
    "PreferenceRepository",
]
