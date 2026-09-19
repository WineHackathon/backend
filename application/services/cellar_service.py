"""
Прикладной сервис винного погреба пользователя.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.cellar import UserCellar
from application.adapters.database.repositories.cellar_repo import CellarRepository
from application.adapters.database.repositories.wine_repo import WineRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.cellar import CellarItemDTO, CellarItemCreateDTO
from application.services.catalog_service import CatalogService
from application.exceptions.domain_exceptions import WineNotFound, CellarItemNotFound


class CellarService:
    """Сервис управления винным погребом и вишлистом пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cellar_repo = CellarRepository(session)
        self.wine_repo = WineRepository(session)
        self.tm = TransactionManager(session)

    def to_dto(self, item: UserCellar) -> CellarItemDTO:
        """Преобразование позиции погреба в DTO."""
        wine_dto = CatalogService.to_dto(item.wine) if item.wine else None
        return CellarItemDTO(
            id=item.id,
            user_id=item.user_id,
            wine_id=item.wine_id,
            status=item.status,
            bottles_count=item.bottles_count,
            personal_rating=item.personal_rating,
            tasting_notes=item.tasting_notes,
            created_at=item.created_at,
            wine=wine_dto,
        )

    async def list_items(self, user_id: uuid.UUID, status: str | None = None) -> list[CellarItemDTO]:
        """Получение списка вин в погребе пользователя."""
        items = await self.cellar_repo.get_user_items(user_id, status=status)
        return [self.to_dto(i) for i in items]

    async def add_item(self, user_id: uuid.UUID, dto: CellarItemCreateDTO) -> CellarItemDTO:
        """Добавление вина в погреб или вишлист."""
        wine = await self.wine_repo.get_by_id(dto.wine_id)
        if not wine:
            raise WineNotFound(str(dto.wine_id))

        existing = await self.cellar_repo.get_by_user_and_wine(user_id, dto.wine_id, dto.status)
        if existing:
            existing.bottles_count += dto.bottles_count
            if dto.personal_rating is not None:
                existing.personal_rating = dto.personal_rating
            if dto.tasting_notes:
                existing.tasting_notes = dto.tasting_notes
            async with self.tm:
                await self.cellar_repo.save(existing)
            return self.to_dto(existing)

        item = UserCellar(
            user_id=user_id,
            wine_id=dto.wine_id,
            status=dto.status,
            bottles_count=dto.bottles_count,
            personal_rating=dto.personal_rating,
            tasting_notes=dto.tasting_notes,
        )
        async with self.tm:
            await self.cellar_repo.save(item)

        item.wine = wine
        return self.to_dto(item)

    async def remove_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        """Удаление позиции из погреба."""
        async with self.tm:
            deleted = await self.cellar_repo.delete_item(user_id, item_id)
        if not deleted:
            raise CellarItemNotFound()
        return True
