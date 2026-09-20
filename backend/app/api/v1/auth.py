"""
Эндпоинты аутентификации и регистрации (/api/v1/auth).
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    TokenPairDTO,
    AuthResponseDTO,
    RefreshTokenRequestDTO,
    YandexAuthDTO,
    LogoutRequestDTO,
    LogoutResponseDTO,
)
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.auth_service import AuthService
from backend.app.config import settings
from backend.app.dependencies import security, get_redis_client

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponseDTO, summary="Register new user")
async def register(
    dto: RegisterRequestDTO,
    x_device_fingerprint: str | None = Header(None, alias="X-Device-Fingerprint"),
    session: AsyncSession = Depends(get_session),
):
    """Регистрация нового пользователя с получением JWT токенов и привязкой истории гостевых сканов."""
    if not dto.device_fingerprint and x_device_fingerprint:
        dto.device_fingerprint = x_device_fingerprint

    service = AuthService(session)
    try:
        user_dto, tokens = await service.register(dto)
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except UserAlreadyExists as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message)


@router.post("/login", response_model=AuthResponseDTO, summary="Login with email and password")
async def login(
    dto: LoginRequestDTO,
    session: AsyncSession = Depends(get_session),
):
    """Вход по email и паролю."""
    service = AuthService(session)
    try:
        user_dto, tokens = await service.login(dto)
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@router.post("/refresh", response_model=AuthResponseDTO, summary="Refresh access token using refresh token")
async def refresh_tokens(
    dto: RefreshTokenRequestDTO,
    redis_client: redis.Redis | None = Depends(get_redis_client),
    session: AsyncSession = Depends(get_session),
):
    """Обновление пары токенов по валидному refresh-токену с проверкой отзыва (blacklist)."""
    service = AuthService(session, redis_client=redis_client)
    try:
        user_dto, tokens = await service.refresh_tokens(dto)
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@router.post("/logout", response_model=LogoutResponseDTO, summary="Logout user and invalidate token")
async def logout(
    dto: LogoutRequestDTO | None = None,
    auth: HTTPAuthorizationCredentials | None = Depends(security),
    redis_client: redis.Redis | None = Depends(get_redis_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Выход из системы (Logout):
    - Принимает опциональный refresh_token (в теле запроса) и/или access_token (в заголовке Authorization).
    - Если Redis доступен, отзывает токены (помещает в blacklist) на время их оставшейся жизни.
    - Возвращает подтверждение успешного выхода.
    """
    service = AuthService(session, redis_client=redis_client)
    await service.logout(
        refresh_token=dto.refresh_token if dto else None,
        access_token=auth.credentials if auth else None,
    )
    return LogoutResponseDTO(status="ok", message="Успешный выход из системы")



@router.get("/yandex/url", summary="Get Yandex ID OAuth authorization URL")
async def get_yandex_auth_url():
    """Получение URL для перенаправления пользователя на авторизацию в Яндекс ID."""
    client_id = settings.yandex_client_id or "dev_yandex_client_id"
    redirect_uri = settings.yandex_redirect_uri
    url = f"https://oauth.yandex.ru/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"
    return {
        "url": url,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }


@router.get("/yandex/callback", response_model=AuthResponseDTO, summary="Handle Yandex ID OAuth redirect callback")
async def yandex_oauth_callback(
    code: str = Query(..., description="Код авторизации от Яндекса"),
    x_device_fingerprint: str | None = Header(None, alias="X-Device-Fingerprint"),
    session: AsyncSession = Depends(get_session),
):
    """Обработка обратного вызова (redirect callback) после авторизации в Яндекс ID."""
    service = AuthService(
        session,
        yandex_client_id=settings.yandex_client_id,
        yandex_client_secret=settings.yandex_client_secret,
        yandex_redirect_uri=settings.yandex_redirect_uri,
    )
    try:
        user_dto, tokens = await service.auth_yandex(
            code=code,
            device_fingerprint=x_device_fingerprint,
        )
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)


@router.post("/yandex", response_model=AuthResponseDTO, summary="Authorize with Yandex ID code from SPA/mobile")
async def auth_yandex(
    dto: YandexAuthDTO,
    x_device_fingerprint: str | None = Header(None, alias="X-Device-Fingerprint"),
    session: AsyncSession = Depends(get_session),
):
    """Авторизация через Яндекс ID по коду (для мобильных приложений и SPA)."""
    service = AuthService(
        session,
        yandex_client_id=settings.yandex_client_id,
        yandex_client_secret=settings.yandex_client_secret,
        yandex_redirect_uri=settings.yandex_redirect_uri,
    )
    try:
        user_dto, tokens = await service.auth_yandex(
            code=dto.code,
            device_fingerprint=x_device_fingerprint,
        )
        return AuthResponseDTO(
            user=user_dto,
            tokens=tokens,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)



