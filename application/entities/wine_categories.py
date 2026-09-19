"""
Доменные перечисления для категорий и типов вин.
"""
import enum


class WineCategory(str, enum.Enum):
    """Категории вин."""
    WHITE = "Белое"
    RED = "Красное"
    ROSE = "Розовое"
    SPARKLING = "Игристое"


class SugarType(str, enum.Enum):
    """Типы вин по содержанию сахара."""
    DRY = "Сухое"
    SEMI_DRY = "Полусухое"
    SEMI_SWEET = "Полусладкое"
    SWEET = "Сладкое"
