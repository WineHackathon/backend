"""
DTO схемы для каталога вин и вкусовой матрицы (Taste Matrix).
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class TasteMatrixDTO(BaseModel):
    """Органолептическая вкусовая матрица вина."""
    sweetness: float | None = Field(default=None, ge=1.0, le=5.0, description="Сладость (1.0 - очень сухое, 5.0 - сладкое)")
    body: float | None = Field(default=None, ge=1.0, le=5.0, description="Тело / плотность (1.0 - легкое, 5.0 - полнотелое)")
    acidity: float | None = Field(default=None, ge=1.0, le=5.0, description="Кислотность (1.0 - мягкая, 5.0 - свежая/высокая)")
    oak: float | None = Field(default=None, ge=1.0, le=5.0, description="Выдержка в дубе (1.0 - без дуба, 5.0 - мощный дуб)")
    aroma_tags: list[str] = Field(default_factory=list, description="Список тегов аромата")
    flavor_tags: list[str] = Field(default_factory=list, description="Список тегов вкусового профиля")
    derived_attributes_confidence: float | None = Field(default=1.0, ge=0.0, le=1.0, description="Уверенность извлечения")


class FoodPairingDTO(BaseModel):
    """Гастрономическое сочетание."""
    id: uuid.UUID
    food_category: str
    dish_name: str
    recommendation_reason: str | None = None

    model_config = {"from_attributes": True}


class WineDTO(BaseModel):
    """Компактное представление карточки вина в каталоге."""
    id: uuid.UUID
    slug: str
    name: str
    category: str
    color_desc: str | None = None
    region: str | None = None
    grape_varieties: list[str] = Field(default_factory=list)
    winery: str | None = None
    roskachestvo_score: float | None = None
    sugar_type: str | None = None
    price_rub: float | None = None
    image_s3_key: str | None = None
    image_url: str | None = None

    # Основные вкусовые шкалы для быстрого отображения радар-чарта
    sweetness: float | None = None
    body: float | None = None
    acidity: float | None = None
    oak: float | None = None

    model_config = {"from_attributes": True}


class WineDetailDTO(WineDTO):
    """Полная детальная карточка вина со всеми органолептическими свойствами и гастропарами."""
    description: str | None = None
    vintage_year: int | None = None
    aroma_tags: list[str] = Field(default_factory=list)
    flavor_tags: list[str] = Field(default_factory=list)
    derived_attributes_confidence: float | None = None
    pairings: list[FoodPairingDTO] = Field(default_factory=list)
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
