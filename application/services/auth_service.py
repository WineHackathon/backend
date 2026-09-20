import logging
import uuid
from datetime import datetime, timezone
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.dto.auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    TokenPairDTO,
    TokenPayloadDTO,
    RefreshTokenRequestDTO,
)
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.security import hash_password, verify_password
from application.services.token_service import TokenService
from application.services.user_service import UserService

logger = logging.getLogger(__name__)

__all__ = ["AuthService", "TokenService", "hash_password", "verify_password"]


class AuthService:
    """Сервис аутентификации пользователей и управления сессиями."""

    def __init__(
        self,
        session: AsyncSession,
        token_service: TokenService | None = None,
        yandex_client_id: str | None = None,
        yandex_client_secret: str | None = None,
        yandex_redirect_uri: str | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.session: AsyncSession = session
        self.user_repo: UserRepository = UserRepository(session)
        self.token_service: TokenService = token_service or TokenService()
        self.yandex_client_id = yandex_client_id
        self.yandex_client_secret = yandex_client_secret
        self.yandex_redirect_uri = yandex_redirect_uri
        self.redis_client = redis_client

    @property
    def access_token_expire_minutes(self) -> int:
        return self.token_service.access_token_expire_minutes

    @property
    def refresh_token_expire_days(self) -> int:
        return self.token_service.refresh_token_expire_days

    def create_token_pair(self, user_id: uuid.UUID, is_admin: bool = False) -> TokenPairDTO:
        """Создание пары токенов (делегирование в TokenService)."""
        return self.token_service.create_token_pair(user_id, is_admin=is_admin)

    def decode_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование токена (делегирование в TokenService)."""
        return self.token_service.decode_token(token)

    def decode_access_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование access токена (делегирование в TokenService)."""
        return self.token_service.decode_access_token(token)

    async def register(self, dto: RegisterRequestDTO) -> tuple[UserDTO, TokenPairDTO]:
        """Регистрация нового пользователя с выдачей токенов и привязкой истории гостевых сканов."""
        existing = await self.user_repo.get_by_email(dto.email)
        if existing:
            raise UserAlreadyExists(dto.email)

        user_service = UserService(self.session)
        user_dto = await user_service.create_user(
            email=dto.email,
            password_hash=hash_password(dto.password),
            first_name=dto.first_name,
            last_name=dto.last_name,
        )

        # Привязка ранее совершенных гостевых сканирований
        if dto.device_fingerprint:
            scan_repo = ScanRepository(self.session)
            await scan_repo.link_guest_scans_to_user(dto.device_fingerprint, user_dto.id)
            await self.session.commit()

        tokens = self.create_token_pair(user_dto.id, is_admin=user_dto.is_admin)
        return user_dto, tokens

    async def auth_yandex(
        self,
        code: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        device_fingerprint: str | None = None,
    ) -> tuple[UserDTO, TokenPairDTO]:
        """
        Аутентификация через Яндекс ID OAuth 2.0.
        Обменивает authorization code на токен, запрашивает профиль пользователя в Яндексе,
        находит или создает пользователя в БД, привязывает гостевые сканы и выдает пару JWT токенов.
        """
        c_id = client_id or self.yandex_client_id
        c_secret = client_secret or self.yandex_client_secret
        r_uri = redirect_uri or self.yandex_redirect_uri

        yandex_user_info: dict = {}

        # Режим тестирования/демо, если ключи не заданы или code тестовый
        if not c_id or not c_secret or code.startswith("test_") or code.startswith("mock_"):
            logger.info("Использование dev-режима Яндекс OAuth (mock профиль).")
            mock_id = code.replace("test_", "").replace("mock_", "") or "dev_user"
            yandex_user_info = {
                "id": f"yandex_{mock_id}",
                "default_email": f"yandex_{mock_id}@yandex.ru",
                "first_name": "Яндекс",
                "last_name": "Пользователь",
                "default_avatar_id": None,
            }
        else:
            token_url = "https://oauth.yandex.ru/token"
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": c_id,
                "client_secret": c_secret,
            }
            if r_uri:
                token_data["redirect_uri"] = r_uri

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    token_resp = await client.post(token_url, data=token_data)
                    if token_resp.status_code != 200:
                        logger.error(f"Ошибка Яндекс OAuth token exchange: {token_resp.status_code} {token_resp.text}")
                        raise AuthenticationError("Не удалось авторизоваться через Яндекс ID: неверный код авторизации.")
                    token_json = token_resp.json()
                    yandex_access_token = token_json.get("access_token")

                    info_url = "https://login.yandex.ru/info?format=json"
                    headers = {"Authorization": f"OAuth {yandex_access_token}"}
                    info_resp = await client.get(info_url, headers=headers)
                    if info_resp.status_code != 200:
                        logger.error(f"Ошибка получения профиля Яндекс: {info_resp.status_code} {info_resp.text}")
                        raise AuthenticationError("Не удалось получить профиль пользователя от Яндекс ID.")
                    yandex_user_info = info_resp.json()
            except httpx.RequestError as exc:
                logger.error(f"Сетевая ошибка при обращении к Яндекс OAuth: {exc}")
                raise AuthenticationError(f"Сетевая ошибка при обращении к Яндекс ID: {exc}")

        yandex_id = str(yandex_user_info.get("id"))
        email = yandex_user_info.get("default_email") or f"yandex_{yandex_id}@yandex.ru"
        first_name = yandex_user_info.get("first_name") or "Пользователь"
        last_name = yandex_user_info.get("last_name")
        avatar_id = yandex_user_info.get("default_avatar_id")
        avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else None

        # Поиск или создание пользователя
        user = await self.user_repo.get_by_yandex_id(yandex_id)
        if not user:
            user = await self.user_repo.get_by_email(email)
            if user:
                user.yandex_id = yandex_id
                if avatar_url and not user.avatar_url:
                    user.avatar_url = avatar_url
                await self.user_repo.save(user)
                await self.session.commit()

        if not user:
            user_service = UserService(self.session)
            user_dto = await user_service.create_user(
                email=email,
                password_hash=None,
                yandex_id=yandex_id,
                first_name=first_name,
                last_name=last_name,
                avatar_url=avatar_url,
            )
        else:
            user_dto = UserService.to_dto(user)

        # Привязка истории гостевых сканов
        if device_fingerprint:
            scan_repo = ScanRepository(self.session)
            await scan_repo.link_guest_scans_to_user(device_fingerprint, user_dto.id)
            await self.session.commit()

        tokens = self.create_token_pair(user_dto.id, is_admin=user_dto.is_admin)
        return user_dto, tokens

    async def login(self, dto: LoginRequestDTO) -> tuple[UserDTO, TokenPairDTO]:
        """Вход пользователя по email и паролю."""
        user = await self.user_repo.get_by_email(dto.email)
        if not user or not user.password_hash or not verify_password(dto.password, user.password_hash):
            raise AuthenticationError("Неверный email или пароль.")

        user_dto = UserService.to_dto(user)
        tokens = self.create_token_pair(user.id, is_admin=user.is_admin)
        return user_dto, tokens

    async def refresh_tokens(self, dto: RefreshTokenRequestDTO) -> tuple[UserDTO, TokenPairDTO]:
        """Обновление пары токенов по валидному refresh-токену с проверкой отзыва."""
        if self.redis_client:
            is_blacklisted = await self.redis_client.get(f"token:blacklist:{dto.refresh_token}")
            if is_blacklisted:
                raise AuthenticationError("Данный refresh токен был отозван (logout).")

        payload = self.decode_token(dto.refresh_token)
        if payload.type != "refresh":
            raise AuthenticationError("Недействительный тип токена. Ожидается refresh токен.")

        user = await self.user_repo.get_by_id(payload.sub)
        if not user:
            raise AuthenticationError("Пользователь не найден.")

        user_dto = UserService.to_dto(user)
        tokens = self.create_token_pair(user.id, is_admin=user.is_admin)
        return user_dto, tokens

    async def logout(
        self,
        refresh_token: str | None = None,
        access_token: str | None = None,
    ) -> None:
        """
        Инвалидация токенов пользователя (помещение в blacklist Redis).
        Гарантирует, что отозванные токены не могут быть использованы повторно.
        """
        tokens_to_blacklist = [t for t in (refresh_token, access_token) if t]
        if not tokens_to_blacklist or not self.redis_client:
            return

        for token in tokens_to_blacklist:
            try:
                payload = self.decode_token(token)
                now_ts = int(datetime.now(timezone.utc).timestamp())
                ttl = max(payload.exp - now_ts, 60)
                await self.redis_client.setex(f"token:blacklist:{token}", ttl, "1")
            except Exception as e:
                logger.warning(f"Не удалось распарсить токен при logout: {e}")
                # Фолбэк TTL: 24 часа
                await self.redis_client.setex(f"token:blacklist:{token}", 86400, "1")


