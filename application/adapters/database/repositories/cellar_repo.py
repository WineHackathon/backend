"""
Репозиторий для работы с личным винным погребом пользователя.
"""
import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from application.adapters.database.models.cellar import UserCellar, CellarStatus


class CellarRepository:
    """Репозиторий винного погреба."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, item: UserCellar) -> UserCellar:
        """Добавление или обновление позиции в погребе."""
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_by_id(self, item_id: uuid.UUID) -> UserCellar | None:
        """Получение позиции погреба по ID."""
        stmt = (
            select(UserCellar)
            .where(UserCellar.id == item_id)
            .options(selectinload(UserCellar.wine))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_user_items(
        self,
        user_id: uuid.UUID,
        status: CellarStatus | str | None = None,
    ) -> Sequence[UserCellar]:
        """Получение всех вин пользователя в погребе с возможностью фильтрации по статусу."""
        stmt = (
            select(UserCellar)
            .where(UserCellar.user_id == user_id)
            .options(selectinload(UserCellar.wine))
            .order_by(UserCellar.created_at.desc())
        )
        if status is not None:
            status_val = status.value if isinstance(status, CellarStatus) else status
            stmt = stmt.where(UserCellar.status == status_val)

        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_by_user_and_wine(
        self,
        user_id: uuid.UUID,
        wine_id: uuid.UUID,
        status: CellarStatus | str,
    ) -> UserCellar | None:
        """Поиск позиции по пользователю, вину и статусу."""
        status_val = status.value if isinstance(status, CellarStatus) else status
        stmt = (
            select(UserCellar)
            .where(
                UserCellar.user_id == user_id,
                UserCellar.wine_id == wine_id,
                UserCellar.status == status_val,
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def delete_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        """Удаление позиции из погреба с проверкой принадлежности пользователю."""
        item = await self.get_by_id(item_id)
        if not item or item.user_id != user_id:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True
