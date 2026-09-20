"""
Эндпоинты аутентификации и регистрации (/api/v1/auth).
Реализует паттерн Thin Handlers: доменные исключения (AuthenticationError, UserAlreadyExists)
автоматически перехватываются глобальными обработчиками в main.py.
"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    AuthResponseDTO,
    RefreshTokenRequestDTO,
    YandexAuthDTO,
    LogoutRequestDTO,
    LogoutResponseDTO,
)
from application.services.auth_service import AuthService
from backend.app.config import settings
from backend.app.dependencies import security, get_redis_client

router = APIRouter(prefix="/api/v1/auth", tags=["Аутентификация и сессии"])


def _extract_request_meta(request: Request, x_device_name: str | None = None) -> tuple[str | None, str | None, str | None]:
    """Извлечение IP-адреса, User-Agent и названия устройства из HTTP-запроса."""
    forwarded = request.headers.get("x-forwarded-for")
    ip_address = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")
    device_name = x_device_name or request.headers.get("x-device-name")
    return ip_address, user_agent, device_name


@router.post("/register", response_model=AuthResponseDTO, summary="Регистрация нового пользователя")
async def register(
    request: Request,
    dto: RegisterRequestDTO,
    session: AsyncSession = Depends(get_session),
):
    """Регистрация нового пользователя с получением JWT токенов, созданием сессии устройства и привязкой истории гостевых сканов."""
    x_device_fingerprint = request.headers.get("x-device-fingerprint")
    if not dto.device_fingerprint and x_device_fingerprint:
        dto.device_fingerprint = x_device_fingerprint

    ip_address, user_agent, extracted_device_name = _extract_request_meta(request)
    device_name = dto.device_name or extracted_device_name
    service = AuthService(session, max_user_sessions=settings.max_user_sessions)

    user_dto, tokens = await service.register(
        dto=dto,
        ip_address=ip_address,
        user_agent=user_agent,
        device_name=device_name,
    )
    return AuthResponseDTO(user=user_dto, tokens=tokens)


@router.post("/login", response_model=AuthResponseDTO, summary="Вход по email и паролю")
async def login(
    request: Request,
    dto: LoginRequestDTO,
    redis_client: redis.Redis | None = Depends(get_redis_client),
    session: AsyncSession = Depends(get_session),
):
    """Вход по email и паролю с созданием сессии устройства и контролем лимита активных устройств (FIFO)."""
    ip_address, user_agent, extracted_device_name = _extract_request_meta(request)
    device_name = dto.device_name or extracted_device_name
    device_fingerprint = dto.device_fingerprint or request.headers.get("x-device-fingerprint")
    service = AuthService(session, redis_client=redis_client, max_user_sessions=settings.max_user_sessions)

    user_dto, tokens = await service.login(
        dto=dto,
        ip_address=ip_address,
        user_agent=user_agent,
        device_name=device_name,
        device_fingerprint=device_fingerprint,
    )
    return AuthResponseDTO(user=user_dto, tokens=tokens)


@router.post("/refresh", response_model=AuthResponseDTO, summary="Обновление пары токенов (refresh)")
async def refresh_tokens(
    request: Request,
    dto: RefreshTokenRequestDTO,
    redis_client: redis.Redis | None = Depends(get_redis_client),
    session: AsyncSession = Depends(get_session),
):
    """Обновление пары токенов по валидному refresh-токену с проверкой сессии в БД и отзыва (blacklist)."""
    ip_address, _, _ = _extract_request_meta(request)
    service = AuthService(session, redis_client=redis_client, max_user_sessions=settings.max_user_sessions)

    user_dto, tokens = await service.refresh_tokens(dto, ip_address=ip_address)
    return AuthResponseDTO(user=user_dto, tokens=tokens)


@router.post("/logout", response_model=LogoutResponseDTO, summary="Выход из системы (logout)")
async def logout(
    dto: LogoutRequestDTO | None = None,
    auth: HTTPAuthorizationCredentials | None = Depends(security),
    redis_client: redis.Redis | None = Depends(get_redis_client),
    session: AsyncSession = Depends(get_session),
):
    """
    Выход из системы (Logout):
    - Удаляет сессию устройства из базы данных.
    - Отзывает токены (помещает в Redis blacklist).
    """
    service = AuthService(session, redis_client=redis_client)
    await service.logout(
        refresh_token=dto.refresh_token if dto else None,
        access_token=auth.credentials if auth else None,
    )
    return LogoutResponseDTO(status="ok", message="Успешный выход из системы")


@router.get("/yandex/url", summary="Получить URL для авторизации через Яндекс ID")
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


@router.get("/yandex/callback", response_model=AuthResponseDTO, summary="Обработка redirect callback от Яндекс ID")
async def yandex_oauth_callback(
    request: Request,
    code: str = Query(..., description="Код авторизации от Яндекса"),
    session: AsyncSession = Depends(get_session),
):
    """Обработка обратного вызова (redirect callback) после авторизации в Яндекс ID."""
    ip_address, user_agent, device_name = _extract_request_meta(request)
    x_device_fingerprint = request.headers.get("x-device-fingerprint")
    service = AuthService(
        session,
        yandex_client_id=settings.yandex_client_id,
        yandex_client_secret=settings.yandex_client_secret,
        yandex_redirect_uri=settings.yandex_redirect_uri,
        max_user_sessions=settings.max_user_sessions,
    )

    user_dto, tokens = await service.auth_yandex(
        code=code,
        device_fingerprint=x_device_fingerprint,
        ip_address=ip_address,
        user_agent=user_agent,
        device_name=device_name,
    )
    return AuthResponseDTO(user=user_dto, tokens=tokens)


@router.post("/yandex", response_model=AuthResponseDTO, summary="Авторизация через Яндекс ID по коду (SPA/mobile)")
async def auth_yandex(
    request: Request,
    dto: YandexAuthDTO,
    session: AsyncSession = Depends(get_session),
):
    """Авторизация через Яндекс ID по коду (для мобильных приложений и SPA)."""
    ip_address, user_agent, extracted_device_name = _extract_request_meta(request)
    device_name = dto.device_name or extracted_device_name
    device_fingerprint = dto.device_fingerprint or request.headers.get("x-device-fingerprint")
    service = AuthService(
        session,
        yandex_client_id=settings.yandex_client_id,
        yandex_client_secret=settings.yandex_client_secret,
        yandex_redirect_uri=settings.yandex_redirect_uri,
        max_user_sessions=settings.max_user_sessions,
    )

    user_dto, tokens = await service.auth_yandex(
        code=dto.code,
        device_fingerprint=device_fingerprint,
        ip_address=ip_address,
        user_agent=user_agent,
        device_name=device_name,
    )
    return AuthResponseDTO(user=user_dto, tokens=tokens)
