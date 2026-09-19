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
    ORANGE = "Оранжевое"
    FORTIFIED = "Ликерное"
    STILL = "Тихое"
    OTHER = "Другое"


class SugarType(str, enum.Enum):
    """Типы вин по содержанию сахара."""
    EXTRA_BRUT = "Экстра брют"
    BRUT = "Брют"
    DRY = "Сухое"
    SEMI_DRY = "Полусухое"
    SEMI_SWEET = "Полусладкое"
    SWEET = "Сладкое"
