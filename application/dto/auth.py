"""
DTO схемы для аутентификации и авторизации.
"""
from pydantic import BaseModel, EmailStr, Field


class LoginRequestDTO(BaseModel):
    """Запрос на вход по Email и паролю."""
    email: EmailStr
    password: str = Field(min_length=6)


class RegisterRequestDTO(BaseModel):
    """Запрос на регистрацию нового пользователя."""
    email: EmailStr
    password: str = Field(min_length=6)
    first_name: str = Field(default="Пользователь")
    last_name: str | None = None


class TokenPairDTO(BaseModel):
    """Пара токенов доступа и обновления."""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class YandexAuthDTO(BaseModel):
    """Запрос авторизации через OAuth Яндекс ID."""
    code: str = Field(description="Authorization code от Яндекса")
