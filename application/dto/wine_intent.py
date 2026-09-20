"""
DTO модели для структурированного извлечения намерений поиска вин.
"""
from typing import Literal
from pydantic import BaseModel, Field


class WineSearchIntent(BaseModel):
    """Структурированные намерения и фильтры, извлеченные из запроса пользователя."""
    category: Literal["Красное", "Белое", "Розовое", "Игристое"] | None = None
    sugar_type: Literal["Сухое", "Полусухое", "Полусладкое", "Сладкое"] | None = None
    food_pairing: str | None = None
    grape_variety: str | None = None
    region: str | None = None
    target_body: float | None = Field(default=None, ge=1.0, le=5.0, description="Шкала плотности/тела вина 1.0 - 5.0")
    target_sweetness: float | None = Field(default=None, ge=1.0, le=5.0, description="Шкала сладости 1.0 - 5.0")
    target_acidity: float | None = Field(default=None, ge=1.0, le=5.0, description="Шкала кислотности 1.0 - 5.0")
    target_oak: float | None = Field(default=None, ge=1.0, le=5.0, description="Шкала выдержки в дубе 1.0 - 5.0")
    max_price_rub: float | None = Field(default=None, gt=0, description="Максимальная цена в рублях")
    search_keywords: list[str] = Field(default_factory=list, description="Ключевые слова для текстового поиска")
    is_recommendation_request: bool = True
