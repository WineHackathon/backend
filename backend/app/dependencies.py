"""
Внедрение зависимостей (Dependency Injection) для FastAPI эндпоинтов.
"""
import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from backend.app.config import settings
from backend.app.services.rate_limiter import ScanRateLimiter
from backend.app.services.ml_dispatcher import MLDispatcher

security = HTTPBearer(auto_error=False)


def get_redis_client(request: Request) -> redis.Redis | None:
    """Получение экземпляра Redis из состояния приложения."""
    return getattr(request.app.state, "redis", None)


def get_rate_limiter(redis_client: redis.Redis | None = Depends(get_redis_client)) -> ScanRateLimiter:
    """Внедрение сервиса ограничения запросов."""
    return ScanRateLimiter(redis_client)


def get_ml_dispatcher(redis_client: redis.Redis | None = Depends(get_redis_client)) -> MLDispatcher:
    """Внедрение диспетчера ML задач."""
    return MLDispatcher(redis_client)


from application.services.auth_service import AuthService

async def get_optional_user_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),
) -> uuid.UUID | None:
    """
    Получение UUID пользователя из JWT токена, если токен передан.
    Проверяет валидность токена и его тип (строго access, предотвращая Token Type Confusion).
    Если токен отсутствует — возвращает None (для анонимных пользователей).
    """
    if not auth:
        return None
    try:
        service = AuthService()
        payload = service.decode_access_token(auth.credentials)
        return payload.sub
    except Exception:
        return None


async def get_current_user_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),
) -> uuid.UUID:
    """
    Строгая проверка аутентификации пользователя.
    Возвращает UUID пользователя или вызывает HTTP 401 Unauthorized.
    """
    user_id = await get_optional_user_id(auth)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация для доступа к ресурсу.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
