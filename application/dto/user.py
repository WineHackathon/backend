"""
DTO схемы для пользователей и вкусового профиля (Taste Profile).
"""
import uuid
from pydantic import BaseModel, Field


class TasteProfileDTO(BaseModel):
    """Агрегированный вкусовой профиль пользователя."""
    preferred_categories: list[str] = Field(default_factory=list, description="Предпочитаемые категории вин")
    sweetness_pref: float = Field(default=2.0, ge=1.0, le=5.0, description="Желаемая сладость")
    body_pref: float = Field(default=3.0, ge=1.0, le=5.0, description="Желаемая плотность/тело")
    acidity_pref: float = Field(default=3.0, ge=1.0, le=5.0, description="Желаемая кислотность")
    oak_pref: float = Field(default=2.5, ge=1.0, le=5.0, description="Желаемая выдержка в дубе")
    favorite_aromas: list[str] = Field(default_factory=list, description="Любимые ноты аромата")
    disliked_aromas: list[str] = Field(default_factory=list, description="Нежелательные ноты аромата")


class UserDTO(BaseModel):
    """Данные пользователя платформы."""
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    is_admin: bool = False
    taste_profile: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}
