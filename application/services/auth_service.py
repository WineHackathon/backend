"""
Прикладной сервис аутентификации пользователей.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.user_repo import UserRepository
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

__all__ = ["AuthService", "TokenService", "hash_password", "verify_password"]


class AuthService:
    """Сервис аутентификации пользователей и управления сессиями."""

    def __init__(
        self,
        session: AsyncSession,
        token_service: TokenService | None = None,
    ) -> None:
        self.session: AsyncSession = session
        self.user_repo: UserRepository = UserRepository(session)
        self.token_service: TokenService = token_service or TokenService()

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
