"""
DTO схемы для аутентификации и авторизации.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from application.dto.user import UserDTO


class TokenPayloadDTO(BaseModel):
    """Строго типизированный payload JWT токена (exp - Unix timestamp NumericDate по RFC 7519)."""
    sub: uuid.UUID
    exp: int
    type: str  # "access" | "refresh"
    is_admin: bool = False
    session_id: uuid.UUID | None = None


class RefreshTokenRequestDTO(BaseModel):
    """Запрос на обновление пары токенов по refresh токену."""
    refresh_token: str


class LoginRequestDTO(BaseModel):
    """Запрос на вход по Email и паролю."""
    email: EmailStr
    password: str = Field(min_length=6)
    device_name: str | None = Field(default=None, description="Название устройства (например, MacBook Pro 16, iPhone 15)")
    device_fingerprint: str | None = Field(default=None, description="Фингерпринт устройства для привязки гостевых сканов")


class RegisterRequestDTO(BaseModel):
    """Запрос на регистрацию нового пользователя."""
    email: EmailStr
    password: str = Field(min_length=6)
    first_name: str = Field(default="Пользователь")
    last_name: str | None = None
    device_name: str | None = Field(default=None, description="Название устройства (например, MacBook Pro 16, iPhone 15)")
    device_fingerprint: str | None = Field(default=None, description="Фингерпринт гостя для привязки истории сканирований")


class TokenPairDTO(BaseModel):
    """Пара токенов доступа и обновления."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class YandexAuthDTO(BaseModel):
    """Запрос авторизации через OAuth Яндекс ID."""
    code: str = Field(description="Authorization code от Яндекса")
    device_name: str | None = Field(default=None, description="Название устройства (например, MacBook Pro 16, iPhone 15)")
    device_fingerprint: str | None = Field(default=None, description="Фингерпринт устройства для привязки гостевых сканов")


class AuthResponseDTO(BaseModel):
    """Ответ аутентификации с данными пользователя и токенами."""
    user: UserDTO
    tokens: TokenPairDTO


class LogoutRequestDTO(BaseModel):
    """Запрос на выход из системы с отзывом токенов."""
    refresh_token: str | None = Field(default=None, description="Refresh токен для отзыва")


class LogoutResponseDTO(BaseModel):
    """Ответ на успешный выход из системы."""
    status: str = "ok"
    message: str = "Успешный выход из системы"


