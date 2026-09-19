"""
Экспорт доменных перечислений.
"""
from .wine_categories import WineCategory, SugarType
from .user_modes import CellarStatus

__all__ = ["WineCategory", "SugarType", "CellarStatus"]
