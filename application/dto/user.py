"""
DTO схемы для пользователей и вкусового профиля (Taste Profile).
"""
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class TasteProfileDTO(BaseModel):
    """Агрегированный вкусовой профиль пользователя."""
    preferred_categories: list[str] = Field(default_factory=list, description="Предпочитаемые категории вин")
    sweetness_pref: float = Field(default=2.0, ge=1.0, le=5.0, description="Желаемая сладость")
    body_pref: float = Field(default=3.0, ge=1.0, le=5.0, description="Желаемая плотность/тело")
    acidity_pref: float = Field(default=3.0, ge=1.0, le=5.0, description="Желаемая кислотность")
    oak_pref: float = Field(default=2.5, ge=1.0, le=5.0, description="Желаемая выдержка в дубе")
    favorite_aromas: list[str] = Field(default_factory=list, description="Любимые ноты аромата")
    disliked_aromas: list[str] = Field(default_factory=list, description="Нежелательные ноты аромата")

    model_config = ConfigDict(from_attributes=True)


class UserDTO(BaseModel):
    """Данные пользователя платформы."""
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    is_admin: bool = False
    role: str = "user"
    taste_profile: TasteProfileDTO | dict[str, Any] = Field(default_factory=TasteProfileDTO)

    model_config = ConfigDict(from_attributes=True)


class UserPreferenceHistoryDTO(BaseModel):
    """Запись истории предпочтений пользователя (сессии сомелье)."""
    id: uuid.UUID
    session_id: str
    raw_answers: dict[str, Any] = Field(default_factory=dict)
    recommended_slugs: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserCreateDTO(BaseModel):
    """Данные для создания нового пользователя."""
    email: str
    password_hash: str | None = None
    yandex_id: str | None = None
    first_name: str = "Пользователь"
    last_name: str | None = None
    avatar_url: str | None = None
    role: str = "user"
    taste_profile: dict[str, Any] = Field(default_factory=dict)


class PreferenceSessionCreateDTO(BaseModel):
    """Данные сессии сомелье для сохранения сырых ответов и обновления вкусового профиля."""
    user_id: uuid.UUID | None = None
    session_id: str
    raw_answers: dict[str, Any] = Field(default_factory=dict)
    recommended_slugs: list[str] = Field(default_factory=list)
