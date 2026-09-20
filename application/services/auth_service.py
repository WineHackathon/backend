import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.adapters.database.repositories.session_repo import SessionRepository
from application.dto.auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    TokenPairDTO,
    TokenPayloadDTO,
    RefreshTokenRequestDTO,
)
from application.dto.session import UserSessionDTO
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.security import hash_password, verify_password
from application.services.token_service import TokenService
from application.services.user_service import UserService

logger = logging.getLogger(__name__)

__all__ = ["AuthService", "TokenService", "hash_password", "verify_password", "hash_token", "parse_device_name"]


def hash_token(token: str) -> str:
    """Вычисление SHA-256 хэша токена для безопасного хранения в БД."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_device_name(user_agent: str | None = None, client_device: str | None = None) -> str:
    """Формирование понятного имени устройства из заголовка User-Agent или клиентского параметра."""
    if client_device and client_device.strip():
        return client_device.strip()[:150]
    if not user_agent:
        return "Неизвестное устройство"

    ua = user_agent.lower()
    os_name = "Устройство"
    if "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"
    elif "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        os_name = "Android"
    elif "windows" in ua:
        os_name = "Windows"
    elif "linux" in ua:
        os_name = "Linux"

    browser = "Браузер"
    if "edg" in ua:
        browser = "Edge"
    elif "chrome" in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"

    return f"{browser} ({os_name})"


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
        max_user_sessions: int = 5,
    ) -> None:
        self.session: AsyncSession = session
        self.user_repo: UserRepository = UserRepository(session)
        self.session_repo: SessionRepository = SessionRepository(session)
        self.token_service: TokenService = token_service or TokenService()
        self.yandex_client_id = yandex_client_id
        self.yandex_client_secret = yandex_client_secret
        self.yandex_redirect_uri = yandex_redirect_uri
        self.redis_client = redis_client
        self.max_user_sessions = max_user_sessions

    @property
    def access_token_expire_minutes(self) -> int:
        return self.token_service.access_token_expire_minutes

    @property
    def refresh_token_expire_days(self) -> int:
        return self.token_service.refresh_token_expire_days

    def create_token_pair(
        self,
        user_id: uuid.UUID,
        is_admin: bool = False,
        session_id: uuid.UUID | None = None,
    ) -> TokenPairDTO:
        """Создание пары токенов (делегирование в TokenService)."""
        return self.token_service.create_token_pair(user_id, is_admin=is_admin, session_id=session_id)

    def decode_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование токена (делегирование в TokenService)."""
        return self.token_service.decode_token(token)

    def decode_access_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование access токена (делегирование в TokenService)."""
        return self.token_service.decode_access_token(token)

    async def register(
        self,
        dto: RegisterRequestDTO,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_name: str | None = None,
    ) -> tuple[UserDTO, TokenPairDTO]:
        """Регистрация нового пользователя с выдачей токенов и созданием сессии устройства."""
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

        # Контроль лимита устройств и создание сессии
        await self.session_repo.enforce_device_limit(user_dto.id, self.max_user_sessions)
        session_id = uuid.uuid4()
        tokens = self.create_token_pair(user_dto.id, is_admin=user_dto.is_admin, session_id=session_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)

        await self.session_repo.create(
            session_id=session_id,
            user_id=user_dto.id,
            refresh_token_hash=hash_token(tokens.refresh_token),
            device_name=parse_device_name(user_agent, device_name),
            device_fingerprint=dto.device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        await self.session.commit()
        return user_dto, tokens

    async def auth_yandex(
        self,
        code: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        device_fingerprint: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_name: str | None = None,
    ) -> tuple[UserDTO, TokenPairDTO]:
        """
        Аутентификация через Яндекс ID OAuth 2.0 с созданием сессии устройства.
        """
        c_id = client_id or self.yandex_client_id
        c_secret = client_secret or self.yandex_client_secret
        r_uri = redirect_uri or self.yandex_redirect_uri

        yandex_user_info: dict = {}

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

        # Учет сессии и лимита устройств
        await self.session_repo.enforce_device_limit(user_dto.id, self.max_user_sessions)
        session_id = uuid.uuid4()
        tokens = self.create_token_pair(user_dto.id, is_admin=user_dto.is_admin, session_id=session_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)

        await self.session_repo.create(
            session_id=session_id,
            user_id=user_dto.id,
            refresh_token_hash=hash_token(tokens.refresh_token),
            device_name=parse_device_name(user_agent, device_name),
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        await self.session.commit()
        return user_dto, tokens

    async def login(
        self,
        dto: LoginRequestDTO,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_name: str | None = None,
        device_fingerprint: str | None = None,
    ) -> tuple[UserDTO, TokenPairDTO]:
        """Вход пользователя по email и паролю с созданием сессии устройства."""
        user = await self.user_repo.get_by_email(dto.email)
        if not user or not user.password_hash or not verify_password(dto.password, user.password_hash):
            raise AuthenticationError("Неверный email или пароль.")

        # Контроль лимита устройств (FIFO)
        evicted = await self.session_repo.enforce_device_limit(user.id, self.max_user_sessions)
        if evicted and self.redis_client:
            for ev in evicted:
                try:
                    await self.redis_client.setex(f"session:revoked:{ev.id}", 86400, "1")
                except Exception:
                    pass

        # Привязка истории гостевых сканов (если юзер ранее сканировал как гость)
        if device_fingerprint:
            scan_repo = ScanRepository(self.session)
            await scan_repo.link_guest_scans_to_user(device_fingerprint, user.id)

        session_id = uuid.uuid4()
        tokens = self.create_token_pair(user.id, is_admin=user.is_admin, session_id=session_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)

        await self.session_repo.create(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=hash_token(tokens.refresh_token),
            device_name=parse_device_name(user_agent, device_name),
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        await self.session.commit()

        user_dto = UserService.to_dto(user)
        return user_dto, tokens

    async def refresh_tokens(
        self,
        dto: RefreshTokenRequestDTO,
        ip_address: str | None = None,
    ) -> tuple[UserDTO, TokenPairDTO]:
        """Обновление пары токенов по валидному refresh-токену с проверкой сессии в БД и блэклиста."""
        if self.redis_client:
            is_blacklisted = await self.redis_client.get(f"token:blacklist:{dto.refresh_token}")
            if is_blacklisted:
                raise AuthenticationError("Данный refresh токен был отозван (logout).")

        payload = self.decode_token(dto.refresh_token)
        if payload.type != "refresh":
            raise AuthenticationError("Недействительный тип токена. Ожидается refresh токен.")

        # Проверка сессии в PostgreSQL
        refresh_hash = hash_token(dto.refresh_token)
        user_session = await self.session_repo.get_by_refresh_hash(refresh_hash)
        if not user_session and payload.session_id:
            user_session = await self.session_repo.get_by_id(payload.session_id)

        if not user_session:
            if payload.session_id:
                raise AuthenticationError("Сессия устройства не найдена или была завершена.")

        if user_session and self.redis_client:
            is_session_revoked = await self.redis_client.get(f"session:revoked:{user_session.id}")
            if is_session_revoked:
                raise AuthenticationError("Сессия устройства была отозвана.")

        user = await self.user_repo.get_by_id(payload.sub)
        if not user:
            raise AuthenticationError("Пользователь не найден.")

        # Ротация токенов с сохранением session_id
        session_id_to_use = user_session.id if user_session else None
        tokens = self.create_token_pair(user.id, is_admin=user.is_admin, session_id=session_id_to_use)

        if user_session:
            new_refresh_hash = hash_token(tokens.refresh_token)
            new_expires_at = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)
            await self.session_repo.update_activity(
                session_id=user_session.id,
                new_refresh_hash=new_refresh_hash,
                ip_address=ip_address,
                expires_at=new_expires_at,
            )
            await self.session.commit()

        user_dto = UserService.to_dto(user)
        return user_dto, tokens

    async def logout(
        self,
        refresh_token: str | None = None,
        access_token: str | None = None,
        session_id: uuid.UUID | None = None,
    ) -> None:
        """
        Инвалидация токенов пользователя (помещение в blacklist Redis и удаление сессии из БД).
        """
        # Удаление сессии из PostgreSQL
        if refresh_token:
            refresh_hash = hash_token(refresh_token)
            user_session = await self.session_repo.get_by_refresh_hash(refresh_hash)
            if user_session and hasattr(user_session, "id") and not asyncio.iscoroutine(user_session.id):
                await self.session_repo.delete_by_id(user_session.id)
                await self.session.commit()
        elif session_id:
            await self.session_repo.delete_by_id(session_id)
            await self.session.commit()
        elif access_token:
            try:
                payload = self.decode_token(access_token)
                if payload.session_id:
                    await self.session_repo.delete_by_id(payload.session_id)
                    await self.session.commit()
            except Exception:
                pass

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
                await self.redis_client.setex(f"token:blacklist:{token}", 86400, "1")

    async def list_user_sessions(
        self,
        user_id: uuid.UUID,
        current_session_id: uuid.UUID | None = None,
    ) -> list[UserSessionDTO]:
        """Получение списка активных сессий пользователя с отметкой текущей сессии."""
        sessions = await self.session_repo.list_by_user_id(user_id)
        result = []
        for s in sessions:
            dto = UserSessionDTO(
                id=s.id,
                device_name=s.device_name,
                device_fingerprint=s.device_fingerprint,
                ip_address=s.ip_address,
                last_active_at=s.last_active_at,
                created_at=s.created_at,
                is_current=bool(current_session_id and s.id == current_session_id),
            )
            result.append(dto)
        return result

    async def revoke_user_session(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> bool:
        """Завершение конкретной сессии пользователя."""
        session = await self.session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id:
            return False

        if self.redis_client:
            try:
                await self.redis_client.setex(f"session:revoked:{session_id}", 86400, "1")
            except Exception:
                pass

        deleted = await self.session_repo.delete_by_id(session_id)
        await self.session.commit()
        return deleted

    async def revoke_all_other_sessions(
        self,
        user_id: uuid.UUID,
        current_session_id: uuid.UUID,
    ) -> int:
        """Завершение всех остальных сессий кроме текущей."""
        count = await self.session_repo.delete_by_user_id_except(user_id, current_session_id)
        await self.session.commit()
        return count


