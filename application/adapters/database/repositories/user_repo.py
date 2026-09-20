"""
Репозиторий для работы с пользователями и их вкусовыми профилями.
"""
import uuid
from typing import Sequence
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from application.adapters.database.models.user import User


class UserRepository:
    """Репозиторий пользователей."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, user: User) -> User:
        """Сохранение или обновление пользователя."""
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Поиск пользователя по UUID."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.cellar_items))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Поиск пользователя по Email (регистронезависимо с нормализацией)."""
        stmt = select(User).where(func.lower(User.email) == email.lower().strip())
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_yandex_id(self, yandex_id: str) -> User | None:
        """Поиск пользователя по Яндекс ID."""
        stmt = select(User).where(User.yandex_id == yandex_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_taste_profile(self, user_id: uuid.UUID, new_profile: dict) -> User | None:
        """Обновление вкусового профиля пользователя."""
        user = await self.get_by_id(user_id)
        if user:
            user.taste_profile = new_profile
            await self.session.flush()
        return user
