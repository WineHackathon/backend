"""
DTO схемы для управления сессиями (устройствами) пользователя.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UserSessionDTO(BaseModel):
    """Информация об активной сессии устройства пользователя."""
    id: uuid.UUID
    device_name: str = Field(description="Понятное имя устройства (Chrome на macOS, iPhone и т.д.)")
    device_fingerprint: str | None = None
    ip_address: str | None = None
    last_active_at: datetime
    created_at: datetime | None = None
    is_current: bool = Field(default=False, description="Является ли сессия текущей (с которой сделан запрос)")

    model_config = ConfigDict(from_attributes=True)


class RevokeSessionResponseDTO(BaseModel):
    """Ответ на завершение конкретной сессии устройства."""
    status: str = "ok"
    revoked_session_id: uuid.UUID
    message: str = "Сессия устройства успешно завершена"

    model_config = ConfigDict(from_attributes=True)


class RevokeAllSessionsResponseDTO(BaseModel):
    """Ответ на завершение всех остальных сессий пользователя."""
    status: str = "ok"
    revoked_count: int
    message: str = "Все остальные сессии успешно завершены"

    model_config = ConfigDict(from_attributes=True)
