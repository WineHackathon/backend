"""
Сервис аутентификации пользователей и управления сессиями.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.adapters.database.repositories.session_repo import SessionRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.adapters.oauth.yandex import YandexOAuthClient, YandexUserProfile
from application.common.device_utils import parse_device_name
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

__all__ = [
    "AuthService",
    "TokenService",
    "hash_password",
    "verify_password",
    "hash_token",
    "parse_device_name",
]


def hash_token(token: str) -> str:
    """Вычисление SHA-256 хэша токена для безопасного хранения в БД."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    """Сервис аутентификации пользователей и управления сессиями."""

    def __init__(
        self,
        session: AsyncSession,
        token_service: TokenService | None = None,
        yandex_client_id: str | None = None,
        yandex_client_secret: str | None = None,
        yandex_redirect_uri: str | None = None,
        yandex_oauth_client: YandexOAuthClient | None = None,
        redis_client: Any | None = None,
        max_user_sessions: int = 5,
    ) -> None:
        self.session: AsyncSession = session
        self.user_repo: UserRepository = UserRepository(session)
        self.session_repo: SessionRepository = SessionRepository(session)
        self.tm: TransactionManager = TransactionManager(session)
        self.token_service: TokenService = token_service or TokenService()
        self.yandex_client: YandexOAuthClient = yandex_oauth_client or YandexOAuthClient(
            client_id=yandex_client_id,
            client_secret=yandex_client_secret,
            redirect_uri=yandex_redirect_uri,
        )
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

    async def _issue_session_and_tokens(
        self,
        user_id: uuid.UUID,
        is_admin: bool,
        device_fingerprint: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_name: str | None = None,
    ) -> TokenPairDTO:
        """
        Единый атомарный метод создания сессии устройства:
        1. Привязка ранее совершенных гостевых сканирований.
        2. Контроль лимита активных устройств (FIFO) с инвалидацией в Redis.
        3. Генерация пары JWT-токенов с session_id.
        4. Сохранение активной сессии устройства в PostgreSQL.
        """
        # 1. Привязка гостевых сканов
        if device_fingerprint:
            scan_repo = ScanRepository(self.session)
            await scan_repo.link_guest_scans_to_user(device_fingerprint, user_id)

        # 2. Контроль лимита устройств (FIFO)
        evicted = await self.session_repo.enforce_device_limit(user_id, self.max_user_sessions)
        if evicted and self.redis_client:
            for ev in evicted:
                try:
                    await self.redis_client.setex(f"session:revoked:{ev.id}", 86400, "1")
                except Exception as exc:
                    logger.warning("Не удалось записать вытесненную сессию в Redis: %s", exc)

        # 3. Выпуск токенов
        session_id = uuid.uuid4()
        tokens = self.create_token_pair(user_id, is_admin=is_admin, session_id=session_id)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)

        # 4. Сохранение сессии в БД
        await self.session_repo.create(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=hash_token(tokens.refresh_token),
            device_name=parse_device_name(user_agent, device_name),
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        await self.session.commit()
        return tokens

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

        tokens = await self._issue_session_and_tokens(
            user_id=user_dto.id,
            is_admin=user_dto.is_admin,
            device_fingerprint=dto.device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
        )
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
        profile: YandexUserProfile = await self.yandex_client.get_user_profile(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )

        # Поиск или создание пользователя
        user = await self.user_repo.get_by_yandex_id(profile.yandex_id)
        if not user:
            user = await self.user_repo.get_by_email(profile.email)
            if user:
                user.yandex_id = profile.yandex_id
                if profile.avatar_url and not user.avatar_url:
                    user.avatar_url = profile.avatar_url
                await self.user_repo.save(user)
                await self.session.commit()

        if not user:
            user_service = UserService(self.session)
            user_dto = await user_service.create_user(
                email=profile.email,
                password_hash=None,
                yandex_id=profile.yandex_id,
                first_name=profile.first_name,
                last_name=profile.last_name,
                avatar_url=profile.avatar_url,
            )
        else:
            user_dto = UserService.to_dto(user)

        tokens = await self._issue_session_and_tokens(
            user_id=user_dto.id,
            is_admin=user_dto.is_admin,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
        )
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

        effective_fingerprint = device_fingerprint or dto.device_fingerprint
        tokens = await self._issue_session_and_tokens(
            user_id=user.id,
            is_admin=user.is_admin,
            device_fingerprint=effective_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
        )
        user_dto = UserService.to_dto(user)
        return user_dto, tokens

    async def refresh_tokens(
        self,
        dto: RefreshTokenRequestDTO,
        ip_address: str | None = None,
    ) -> tuple[UserDTO, TokenPairDTO]:
        """Обновление пары токенов по валидному refresh-токену с проверкой сессии в БД и блэклиста."""
        if self.redis_client:
            try:
                is_blacklisted = await self.redis_client.get(f"token:blacklist:{dto.refresh_token}")
                if is_blacklisted:
                    raise AuthenticationError("Данный refresh токен был отозван (logout).")
            except AuthenticationError:
                raise
            except Exception as exc:
                logger.warning("Ошибка проверки токена в Redis blacklist: %s", exc)

        payload = self.decode_token(dto.refresh_token)
        if payload.type != "refresh":
            raise AuthenticationError("Недействительный тип токена. Ожидается refresh токен.")

        # Проверка сессии в PostgreSQL
        refresh_hash = hash_token(dto.refresh_token)
        user_session = await self.session_repo.get_by_refresh_hash(refresh_hash)
        if not user_session and payload.session_id:
            user_session = await self.session_repo.get_by_id(payload.session_id)

        if not user_session and payload.session_id:
            raise AuthenticationError("Сессия устройства не найдена или была завершена.")

        if user_session and self.redis_client:
            try:
                is_session_revoked = await self.redis_client.get(f"session:revoked:{user_session.id}")
                if is_session_revoked:
                    raise AuthenticationError("Сессия устройства была отозвана.")
            except AuthenticationError:
                raise
            except Exception as exc:
                logger.warning("Ошибка проверки отзыва сессии в Redis: %s", exc)

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
        target_session_id: uuid.UUID | None = session_id

        # 1. Определение session_id по refresh-токену
        if not target_session_id and refresh_token:
            refresh_hash = hash_token(refresh_token)
            user_session = await self.session_repo.get_by_refresh_hash(refresh_hash)
            if user_session:
                target_session_id = user_session.id

        # 2. Определение session_id по access-токену
        if not target_session_id and access_token:
            try:
                payload = self.decode_token(access_token)
                target_session_id = payload.session_id
            except Exception as exc:
                logger.debug("Не удалось извлечь session_id из access токена: %s", exc)

        # 3. Удаление сессии из PostgreSQL
        if target_session_id:
            await self.session_repo.delete_by_id(target_session_id)
            await self.session.commit()

        # 4. Добавление токенов в blacklist Redis
        tokens_to_blacklist = [t for t in (refresh_token, access_token) if t]
        if not tokens_to_blacklist or not self.redis_client:
            return

        for token in tokens_to_blacklist:
            try:
                payload = self.decode_token(token)
                now_ts = int(datetime.now(timezone.utc).timestamp())
                ttl = max(payload.exp - now_ts, 60)
                await self.redis_client.setex(f"token:blacklist:{token}", ttl, "1")
            except Exception as exc:
                logger.warning("Не удалось распарсить токен при logout: %s", exc)
                try:
                    await self.redis_client.setex(f"token:blacklist:{token}", 86400, "1")
                except Exception as redis_err:
                    logger.warning("Ошибка записи токена в Redis blacklist: %s", redis_err)

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
            except Exception as exc:
                logger.warning("Ошибка отзыва сессии в Redis: %s", exc)

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
