"""
Прикладной сервис пользователей и управления профилем.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.user import User, UserRole
from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.adapters.database.repositories.preference_repo import PreferenceRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.user import UserDTO, UserCreateDTO, UserPreferenceHistoryDTO
from application.dto.scan import ScanHistoryItemDTO
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
        role_val = user.role.value if hasattr(user.role, "value") else str(user.role or "user")
        return UserDTO(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            avatar_url=user.avatar_url,
            is_active=bool(user.is_active) if user.is_active is not None else True,
            is_admin=bool(user.is_admin) if user.is_admin is not None else False,
            role=role_val,
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
        dto: UserCreateDTO | None = None,
        **kwargs,
    ) -> UserDTO:
        """Создание нового пользователя через UserCreateDTO."""
        if dto is None:
            dto = UserCreateDTO(**kwargs)
        elif kwargs:
            dto = dto.model_copy(update=kwargs)

        existing = await self.repo.get_by_email(dto.email)
        if existing:
            raise UserAlreadyExists(dto.email)

        role_val = UserRole.USER
        if hasattr(dto, "role") and dto.role:
            try:
                role_val = UserRole(dto.role.lower())
            except ValueError:
                role_val = UserRole.USER

        user = User(
            id=uuid.uuid4(),
            email=dto.email.lower().strip(),
            password_hash=dto.password_hash,
            yandex_id=dto.yandex_id,
            first_name=dto.first_name,
            last_name=dto.last_name,
            avatar_url=dto.avatar_url,
            role=role_val,
            taste_profile=dto.taste_profile or {},
        )

        async with self.tm:
            await self.repo.save(user)

        return self.to_dto(user)

    async def get_user_scans(self, user_id: uuid.UUID, limit: int = 20) -> list[ScanHistoryItemDTO]:
        """Получение истории сканирований пользователя."""
        repo = ScanRepository(self.session)
        scans = await repo.get_user_scans(user_id, limit=limit)
        return [
            ScanHistoryItemDTO(
                id=s.id,
                image_id=s.image_id,
                predicted_slug=s.predicted_slug,
                confidence=s.confidence,
                latency_ms=s.latency_ms,
                status=s.status,
                created_at=s.created_at,
            )
            for s in scans
        ]

    async def get_user_preferences(self, user_id: uuid.UUID, limit: int = 10) -> list[UserPreferenceHistoryDTO]:
        """Получение истории предпочтений пользователя в диалогах с сомелье."""
        repo = PreferenceRepository(self.session)
        items = await repo.get_by_user_id(user_id, limit=limit)
        return [
            UserPreferenceHistoryDTO(
                id=item.id,
                session_id=item.session_id,
                raw_answers=item.raw_answers,
                recommended_slugs=item.recommended_slugs,
                created_at=item.created_at,
            )
            for item in items
        ]
