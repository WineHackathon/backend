"""
Внедрение зависимостей (Dependency Injection) для FastAPI эндпоинтов.
"""
import uuid
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.adapters.ml.ml_dispatcher import MLDispatcher
from application.adapters.redis.rate_limiter import ScanRateLimiter
from application.services.token_service import TokenService
from backend.app.config import settings

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


async def get_optional_user_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> uuid.UUID | None:
    """
    Получение UUID пользователя из JWT токена, если токен передан.
    Проверяет валидность токена и его тип (строго access, предотвращая Token Type Confusion).
    Проверяет, не был ли токен отозван (в черном списке Redis после logout).
    Если токен отсутствует или отозван — возвращает None (для анонимных пользователей).
    """
    if not auth:
        return None
    try:
        if redis_client:
            is_blacklisted = await redis_client.get(f"token:blacklist:{auth.credentials}")
            if is_blacklisted:
                return None

        token_service = TokenService()
        payload = token_service.decode_access_token(auth.credentials)
        return payload.sub
    except Exception:
        return None


async def get_current_user_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> uuid.UUID:
    """
    Строгая проверка аутентификации пользователя.
    Возвращает UUID пользователя или вызывает HTTP 401 Unauthorized.
    """
    user_id = await get_optional_user_id(auth, redis_client=redis_client)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация для доступа к ресурсу.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


async def get_current_session_id(
    auth: HTTPAuthorizationCredentials | None = Depends(security),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> uuid.UUID | None:
    """Получение session_id текущего устройства из JWT токена."""
    if not auth:
        return None
    try:
        if redis_client:
            is_blacklisted = await redis_client.get(f"token:blacklist:{auth.credentials}")
            if is_blacklisted:
                return None

        token_service = TokenService()
        payload = token_service.decode_access_token(auth.credentials)
        return payload.session_id
    except Exception:
        return None

