"""
Репозиторий для сохранения истории предпочтений пользователя и рекомендаций сомелье.
"""
import uuid
from typing import Sequence
from sqlalchemy import select, update
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

    async def get_by_session_id(self, session_id: str) -> UserPreferenceHistory | None:
        """Получение записи предпочтений по идентификатору сессии диалога."""
        stmt = select(UserPreferenceHistory).where(UserPreferenceHistory.session_id == session_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def link_guest_preferences_to_user(self, session_id: str, user_id: uuid.UUID) -> int:
        """Привязка гостевой сессии предпочтений к зарегистрированному пользователю."""
        stmt = (
            update(UserPreferenceHistory)
            .where(
                UserPreferenceHistory.session_id == session_id,
                UserPreferenceHistory.user_id.is_(None),
            )
            .values(user_id=user_id)
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount or 0
