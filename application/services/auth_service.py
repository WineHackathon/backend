"""
Прикладной сервис аутентификации и генерации JWT токенов.
"""
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
import jwt
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    TokenPairDTO,
    TokenPayloadDTO,
    RefreshTokenRequestDTO,
)
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.user_service import UserService


class AuthSettings(BaseSettings):
    """Настройки аутентификации и JWT токенов (независимы от веб-фреймворка)."""
    jwt_secret_key: str = "wine_hackathon_super_secret_jwt_key_32_chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30
    password_salt: str = "wine_salt_hackathon_2026"

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "case_sensitive": False,
    }


auth_settings = AuthSettings()


def hash_password(password: str) -> str:
    """Хеширование пароля через PBKDF2-HMAC-SHA256 (100,000 итераций) с уникальной криптографической солью."""
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return f"pbkdf2_sha256$100000${salt}${derived.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Проверка пароля через PBKDF2-HMAC-SHA256 с поддержкой модульного формата crypt и обратной совместимости."""
    if not hashed or not hashed.startswith("pbkdf2_sha256$"):
        return False
    parts = hashed.split("$")

    # Стандартный модульный формат: pbkdf2_sha256$<iterations>$<salt>$<hash>
    if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
        try:
            iterations = int(parts[1])
        except ValueError:
            return False
        salt = parts[2]
        expected_hash = parts[3]
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(derived, expected_hash)

    # Устаревший 2-элементный формат: pbkdf2_sha256$<hash> (обратная совместимость)
    elif len(parts) == 2 and parts[0] == "pbkdf2_sha256":
        expected = parts[1]
        legacy_salt = auth_settings.password_salt
        derived_legacy = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            legacy_salt.encode("utf-8"),
            100_000,
        ).hex()
        return hmac.compare_digest(derived_legacy, expected)

    return False


class TokenService:
    """Сервис создания, подписи и верификации JWT токенов (не требует сессии БД)."""

    def __init__(
        self,
        jwt_secret: str | None = None,
        jwt_algorithm: str | None = None,
        access_token_expire_minutes: int | None = None,
        refresh_token_expire_days: int | None = None,
    ) -> None:
        self.jwt_secret = jwt_secret or auth_settings.jwt_secret_key
        self.jwt_algorithm = jwt_algorithm or auth_settings.jwt_algorithm
        self.access_token_expire_minutes = (
            access_token_expire_minutes or auth_settings.jwt_access_token_expire_minutes
        )
        self.refresh_token_expire_days = (
            refresh_token_expire_days or auth_settings.jwt_refresh_token_expire_days
        )

    def create_token_pair(self, user_id: uuid.UUID, is_admin: bool = False) -> TokenPairDTO:
        """Создание пары токенов (access и refresh) с валидацией через TokenPayloadDTO."""
        now = datetime.now(timezone.utc)
        access_exp = int((now + timedelta(minutes=self.access_token_expire_minutes)).timestamp())
        refresh_exp = int((now + timedelta(days=self.refresh_token_expire_days)).timestamp())

        access_payload = TokenPayloadDTO(
            sub=user_id,
            is_admin=is_admin,
            exp=access_exp,
            type="access",
        )
        refresh_payload = TokenPayloadDTO(
            sub=user_id,
            exp=refresh_exp,
            type="refresh",
        )

        access_token = jwt.encode(
            access_payload.model_dump(mode="json"),
            self.jwt_secret,
            algorithm=self.jwt_algorithm,
        )
        refresh_token = jwt.encode(
            refresh_payload.model_dump(mode="json"),
            self.jwt_secret,
            algorithm=self.jwt_algorithm,
        )

        return TokenPairDTO(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=int(self.access_token_expire_minutes * 60),
        )

    def decode_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование и верификация JWT токена в строгий TokenPayloadDTO."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return TokenPayloadDTO.model_validate(payload)
        except (jwt.PyJWTError, Exception) as e:
            raise AuthenticationError(f"Недействительный токен: {str(e)}")

    def decode_access_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование access-токена с защитой от подмены типа (Token Type Confusion)."""
        payload = self.decode_token(token)
        if payload.type != "access":
            raise AuthenticationError("Недействительный тип токена. Ожидается access токен.")
        return payload


class AuthService:
    """Сервис аутентификации пользователей."""

    def __init__(
        self,
        session: AsyncSession,
        token_service: TokenService | None = None,
    ) -> None:
        self.session: AsyncSession = session
        self.user_repo: UserRepository = UserRepository(session)
        self.tm: TransactionManager = TransactionManager(session)
        self.token_service: TokenService = token_service or TokenService()

    @property
    def access_token_expire_minutes(self) -> int:
        return self.token_service.access_token_expire_minutes

    @property
    def refresh_token_expire_days(self) -> int:
        return self.token_service.refresh_token_expire_days

    def create_token_pair(self, user_id: uuid.UUID, is_admin: bool = False) -> TokenPairDTO:
        """Делегирование создания токенов в TokenService."""
        return self.token_service.create_token_pair(user_id, is_admin=is_admin)

    def decode_token(self, token: str) -> TokenPayloadDTO:
        """Делегирование декодирования токена в TokenService."""
        return self.token_service.decode_token(token)

    def decode_access_token(self, token: str) -> TokenPayloadDTO:
        """Делегирование декодирования access токена в TokenService."""
        return self.token_service.decode_access_token(token)

    async def register(self, dto: RegisterRequestDTO) -> tuple[UserDTO, TokenPairDTO]:
        """Регистрация нового пользователя с выдачей токенов."""
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
        """Обновление пары токенов по валидному refresh-токену."""
        payload = self.decode_token(dto.refresh_token)
        if payload.type != "refresh":
            raise AuthenticationError("Недействительный тип токена. Ожидается refresh токен.")

        user = await self.user_repo.get_by_id(payload.sub)
        if not user:
            raise AuthenticationError("Пользователь не найден.")

        user_dto = UserService.to_dto(user)
        tokens = self.create_token_pair(user.id, is_admin=user.is_admin)
        return user_dto, tokens
