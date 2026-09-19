"""
DTO схемы для личного винного погреба.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from application.adapters.database.models.cellar import CellarStatus
from application.dto.wine import WineDTO


class CellarItemCreateDTO(BaseModel):
    """Запрос на добавление вина в погреб или вишлист."""
    wine_id: uuid.UUID
    status: CellarStatus = Field(default=CellarStatus.IN_CELLAR, description="Статус: in_cellar, wishlist, tasted")
    bottles_count: int = Field(default=1, ge=1)
    personal_rating: int | None = Field(default=None, ge=1, le=5)
    tasting_notes: str | None = None


class CellarItemDTO(BaseModel):
    """Данные позиции в винном погребе."""
    id: uuid.UUID
    user_id: uuid.UUID
    wine_id: uuid.UUID
    status: CellarStatus
    bottles_count: int
    personal_rating: int | None = None
    tasting_notes: str | None = None
    created_at: datetime
    wine: WineDTO | None = None

    model_config = {"from_attributes": True}


class CellarDeleteResponseDTO(BaseModel):
    """Ответ при успешном удалении позиции из погреба."""
    status: str = "deleted"
    item_id: uuid.UUID

