"""
Прикладной сервис пользователей и управления профилем.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.user import User
from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.user import UserDTO
from application.exceptions.domain_exceptions import UserNotFound, UserAlreadyExists


class UserService:
    """Сервис управления пользователями."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)
        self.tm = TransactionManager(session)

    @staticmethod
    def to_dto(user: User) -> UserDTO:
        """Преобразование модели User в UserDTO."""
        return UserDTO(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            is_active=user.is_active,
            is_admin=user.is_admin,
            taste_profile=user.taste_profile or {},
        )

    async def get_by_id(self, user_id: uuid.UUID) -> UserDTO:
        """Получение данных пользователя по UUID."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise UserNotFound(str(user_id))
        return self.to_dto(user)

    async def get_by_email(self, email: str) -> UserDTO | None:
        """Поиск пользователя по email."""
        user = await self.repo.get_by_email(email)
        if not user:
            return None
        return self.to_dto(user)

    async def create_user(
        self,
        email: str,
        password_hash: str | None = None,
        yandex_id: str | None = None,
        first_name: str = "Пользователь",
        last_name: str | None = None,
        avatar_url: str | None = None,
        taste_profile: dict | None = None,
    ) -> UserDTO:
        """Создание нового пользователя."""
        existing = await self.repo.get_by_email(email)
        if existing:
            raise UserAlreadyExists(email)

        user = User(
            email=email.lower().strip(),
            password_hash=password_hash,
            yandex_id=yandex_id,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
            taste_profile=taste_profile or {},
        )

        async with self.tm:
            await self.repo.save(user)

        return self.to_dto(user)
