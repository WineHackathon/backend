"""
Репозиторий для сохранения истории предпочтений пользователя и рекомендаций сомелье.
"""
import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.preference_history import UserPreferenceHistory


class PreferenceRepository:
    """Репозиторий истории предпочтений."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, record: UserPreferenceHistory) -> UserPreferenceHistory:
        """Сохранение истории сессии сомелье."""
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_user_id(
        self,
        user_id: uuid.UUID,
        limit: int = 10,
    ) -> Sequence[UserPreferenceHistory]:
        """Получение последних сессий предпочтений пользователя."""
        stmt = (
            select(UserPreferenceHistory)
            .where(UserPreferenceHistory.user_id == user_id)
            .order_by(UserPreferenceHistory.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()
