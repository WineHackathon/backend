"""
Прикладной сервис винного погреба пользователя.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.cellar import UserCellar, CellarStatus
from application.adapters.database.repositories.cellar_repo import CellarRepository
from application.adapters.database.repositories.wine_repo import WineRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.cellar import CellarItemDTO, CellarItemCreateDTO, CellarItemUpdateDTO
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
            created_at=item.created_at or datetime.now(timezone.utc),
            wine=wine_dto,
        )

    async def list_items(self, user_id: uuid.UUID, status: CellarStatus | str | None = None) -> list[CellarItemDTO]:
        """Получение списка вин в погребе пользователя."""
        items = await self.cellar_repo.get_user_items(user_id, status=status)
        return [self.to_dto(i) for i in items]

    async def add_item(self, user_id: uuid.UUID, dto: CellarItemCreateDTO) -> CellarItemDTO:
        """Добавление вина в погреб или вишлист (по wine_id или wine_slug)."""
        wine = None
        if dto.wine_id:
            wine = await self.wine_repo.get_by_id(dto.wine_id)
        elif dto.wine_slug:
            wine = await self.wine_repo.get_by_slug(dto.wine_slug)

        if not wine:
            target = str(dto.wine_id or dto.wine_slug or "не указан")
            raise WineNotFound(target)

        wine_id = wine.id
        # Если добавляем в погреб (in_cellar), удаляем из вишлиста если оно там было
        if dto.status == CellarStatus.IN_CELLAR or dto.status == "in_cellar":
            wishlist_item = await self.cellar_repo.get_by_user_and_wine(user_id, wine_id, CellarStatus.WISHLIST)
            if wishlist_item:
                await self.cellar_repo.delete_item(user_id, wishlist_item.id)

        existing = await self.cellar_repo.get_by_user_and_wine(user_id, wine_id, dto.status)
        if existing:
            existing.bottles_count += dto.bottles_count
            if dto.personal_rating is not None:
                existing.personal_rating = dto.personal_rating
            if dto.tasting_notes:
                existing.tasting_notes = dto.tasting_notes
            async with self.tm:
                await self.cellar_repo.save(existing)
            existing.wine = wine
            return self.to_dto(existing)

        item = UserCellar(
            id=uuid.uuid4(),
            user_id=user_id,
            wine_id=wine_id,
            status=dto.status,
            bottles_count=dto.bottles_count,
            personal_rating=dto.personal_rating,
            tasting_notes=dto.tasting_notes,
            created_at=datetime.now(timezone.utc),
        )
        async with self.tm:
            await self.cellar_repo.save(item)

        item.wine = wine
        return self.to_dto(item)

    async def update_item(
        self,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        dto: CellarItemUpdateDTO,
    ) -> CellarItemDTO:
        """Обновление позиции в личном погребе (статус, оценка, заметка, количество)."""
        item = await self.cellar_repo.get_by_id(item_id)
        if not item or item.user_id != user_id:
            raise CellarItemNotFound()

        async with self.tm:
            # Если меняется статус позиции (например, из in_cellar в tasted)
            if dto.status is not None and dto.status != item.status:
                existing = await self.cellar_repo.get_by_user_and_wine(user_id, item.wine_id, dto.status)
                if existing and existing.id != item.id:
                    # Слияние с существующей позицией в новом статусе (защита от нарушения unique constraint)
                    if dto.bottles_count is not None:
                        existing.bottles_count = dto.bottles_count
                    else:
                        existing.bottles_count += item.bottles_count

                    if dto.personal_rating is not None:
                        existing.personal_rating = dto.personal_rating
                    elif item.personal_rating is not None and existing.personal_rating is None:
                        existing.personal_rating = item.personal_rating

                    if dto.tasting_notes is not None:
                        existing.tasting_notes = dto.tasting_notes
                    elif item.tasting_notes is not None and not existing.tasting_notes:
                        existing.tasting_notes = item.tasting_notes

                    await self.cellar_repo.delete_item(user_id, item.id)
                    await self.cellar_repo.save(existing)
                    return self.to_dto(existing)
                else:
                    item.status = dto.status

            if dto.bottles_count is not None:
                item.bottles_count = dto.bottles_count
            if dto.personal_rating is not None:
                item.personal_rating = dto.personal_rating
            if dto.tasting_notes is not None:
                item.tasting_notes = dto.tasting_notes

            await self.cellar_repo.save(item)

        return self.to_dto(item)

    async def remove_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        """Удаление позиции из погреба."""
        async with self.tm:
            deleted = await self.cellar_repo.delete_item(user_id, item_id)
        if not deleted:
            raise CellarItemNotFound()
        return True
