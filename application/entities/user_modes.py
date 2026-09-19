"""
Доменные перечисления для статусов винного погреба и пользователей.
"""
import enum


class CellarStatus(str, enum.Enum):
    """Статусы бутылки в погребе пользователя."""
    IN_CELLAR = "in_cellar"
    WISHLIST = "wishlist"
    TASTED = "tasted"
