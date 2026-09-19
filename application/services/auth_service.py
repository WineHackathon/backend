"""
Прикладной сервис аутентификации и генерации JWT токенов.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
import hashlib
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.auth import LoginRequestDTO, RegisterRequestDTO, TokenPairDTO
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import AuthenticationError, UserAlreadyExists
from application.services.user_service import UserService


def hash_password(password: str) -> str:
    """Хеширование пароля через SHA-256 с солью (в production: argon2id/bcrypt)."""
    salt = os.getenv("PASSWORD_SALT", "wine_salt_hackathon_2026")
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Проверка соответствия пароля хешу."""
    return hash_password(password) == hashed


class AuthService:
    """Сервис аутентификации пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.tm = TransactionManager(session)
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "wine_hackathon_super_secret_jwt_key_32_chars")
        self.jwt_algorithm = "HS256"

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
