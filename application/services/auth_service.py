"""
Прикладной сервис аутентификации и генерации JWT токенов.
"""
import uuid
from datetime import datetime, timedelta, timezone
import hashlib
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.auth import LoginRequestDTO, RegisterRequestDTO, TokenPairDTO
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.user_service import UserService


def hash_password(password: str, salt: str | None = None) -> str:
    """Хеширование пароля через SHA-256 с солью из конфигурации."""
    used_salt = salt or settings.password_salt
    return hashlib.sha256(f"{used_salt}{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str, salt: str | None = None) -> bool:
    """Проверка соответствия пароля хешу."""
    return hash_password(password, salt=salt) == hashed


class AuthService:
    """Сервис аутентификации пользователей."""

    def __init__(
        self,
        session: AsyncSession,
        jwt_secret: str | None = None,
        jwt_algorithm: str | None = None,
        password_salt: str | None = None,
    ) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.tm = TransactionManager(session)
        self.jwt_secret = jwt_secret or settings.jwt_secret_key
        self.jwt_algorithm = jwt_algorithm or settings.jwt_algorithm
        self.password_salt = password_salt or settings.password_salt

    def create_token_pair(self, user_id: uuid.UUID, is_admin: bool = False) -> TokenPairDTO:
        """Создание пары токенов (access и refresh)."""
        now = datetime.now(timezone.utc)
        access_exp = now + timedelta(minutes=60)
        refresh_exp = now + timedelta(days=30)

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
            expires_in=3600,
        )

    def decode_token(self, token: str) -> dict:
        """Декодирование и верификация JWT токена."""
        try:
            return jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
        except jwt.PyJWTError as e:
            raise AuthenticationError(f"Недействительный токен: {str(e)}")

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
