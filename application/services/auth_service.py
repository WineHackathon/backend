"""
Прикладной сервис аутентификации и генерации JWT токенов.
"""
import hmac
import uuid
from datetime import datetime, timedelta, timezone
import hashlib
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
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


def hash_password(password: str, salt: str | None = None) -> str:
    """Хеширование пароля через PBKDF2-HMAC-SHA256 (100,000 итераций)."""
    used_salt = salt or settings.password_salt
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), used_salt.encode("utf-8"), 100_000)
    return f"pbkdf2_sha256${derived.hex()}"


def verify_password(password: str, hashed: str, salt: str | None = None) -> bool:
    """Проверка пароля с поддержкой PBKDF2 и обратной совместимостью для SHA-256."""
    used_salt = salt or settings.password_salt
    if hashed.startswith("pbkdf2_sha256$"):
        expected = hashed.split("$", 1)[1]
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), used_salt.encode("utf-8"), 100_000).hex()
        return hmac.compare_digest(derived, expected)
    # Обратная совместимость для legacy SHA-256 хешей
    legacy = hashlib.sha256(f"{used_salt}{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, hashed)


class AuthService:
    """Сервис аутентификации пользователей."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        jwt_secret: str | None = None,
        jwt_algorithm: str | None = None,
        password_salt: str | None = None,
        access_token_expire_minutes: int | None = None,
        refresh_token_expire_days: int | None = None,
    ) -> None:
        self.session = session
        self.user_repo = UserRepository(session) if session else None
        self.tm = TransactionManager(session) if session else None
        self.jwt_secret = jwt_secret or settings.jwt_secret_key
        self.jwt_algorithm = jwt_algorithm or settings.jwt_algorithm
        self.password_salt = password_salt or settings.password_salt
        self.access_token_expire_minutes = (
            access_token_expire_minutes or settings.jwt_access_token_expire_minutes
        )
        self.refresh_token_expire_days = (
            refresh_token_expire_days or settings.jwt_refresh_token_expire_days
        )

    def create_token_pair(self, user_id: uuid.UUID, is_admin: bool = False) -> TokenPairDTO:
        """Создание пары токенов (access и refresh) с временем жизни из настроек."""
        now = datetime.now(timezone.utc)
        access_exp = now + timedelta(minutes=self.access_token_expire_minutes)
        refresh_exp = now + timedelta(days=self.refresh_token_expire_days)

        access_payload = {
            "sub": str(user_id),
            "is_admin": is_admin,
            "exp": access_exp,
            "type": "access",
        }
        refresh_payload = {
            "sub": str(user_id),
            "exp": refresh_exp,
            "type": "refresh",
        }

        access_token = jwt.encode(access_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        refresh_token = jwt.encode(refresh_payload, self.jwt_secret, algorithm=self.jwt_algorithm)

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
        except jwt.PyJWTError as e:
            raise AuthenticationError(f"Недействительный токен: {str(e)}")

    def decode_access_token(self, token: str) -> TokenPayloadDTO:
        """Декодирование access-токена с защитой от подмены типа (Token Type Confusion)."""
        payload = self.decode_token(token)
        if payload.type != "access":
            raise AuthenticationError("Недействительный тип токена. Ожидается access токен.")
        return payload

    async def register(self, dto: RegisterRequestDTO) -> tuple[UserDTO, TokenPairDTO]:
        """Регистрация нового пользователя с выдачей токенов."""
        existing = await self.user_repo.get_by_email(dto.email)
        if existing:
            raise UserAlreadyExists(dto.email)

        user_service = UserService(self.session)
        user_dto = await user_service.create_user(
            email=dto.email,
            password_hash=hash_password(dto.password, salt=self.password_salt),
            first_name=dto.first_name,
            last_name=dto.last_name,
        )
        tokens = self.create_token_pair(user_dto.id, is_admin=user_dto.is_admin)
        return user_dto, tokens

    async def login(self, dto: LoginRequestDTO) -> tuple[UserDTO, TokenPairDTO]:
        """Вход пользователя по email и паролю."""
        user = await self.user_repo.get_by_email(dto.email)
        if not user or not user.password_hash or not verify_password(dto.password, user.password_hash, salt=self.password_salt):
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
