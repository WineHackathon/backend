"""
Репозиторий активных сессий устройств пользователя (SessionRepository).
"""
import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.user_session import UserSession


class SessionRepository:
    """Репозиторий для работы с активными сессиями устройств в PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        device_name: str,
        expires_at: datetime,
        session_id: uuid.UUID | None = None,
        device_fingerprint: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> UserSession:
        """Создание новой сессии устройства."""
        user_session = UserSession(
            id=session_id or uuid.uuid4(),
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            device_name=device_name,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            last_active_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        self.session.add(user_session)
        res = self.session.flush()
        if asyncio.iscoroutine(res):
            await res
        return user_session

    async def get_by_id(self, session_id: uuid.UUID) -> UserSession | None:
        """Поиск сессии по ID."""
        stmt = select(UserSession).where(UserSession.id == session_id)
        result = await self.session.execute(stmt)
        val = result.scalar_one_or_none()
        if asyncio.iscoroutine(val):
            val = await val
        return val if isinstance(val, UserSession) else None

    async def get_by_refresh_hash(self, refresh_token_hash: str) -> UserSession | None:
        """Поиск сессии по хэшу refresh-токена."""
        stmt = select(UserSession).where(UserSession.refresh_token_hash == refresh_token_hash)
        result = await self.session.execute(stmt)
        val = result.scalar_one_or_none()
        if asyncio.iscoroutine(val):
            val = await val
        return val if isinstance(val, UserSession) else None

    async def list_by_user_id(self, user_id: uuid.UUID) -> list[UserSession]:
        """Список всех активных сессий пользователя, упорядоченных по дате последней активности."""
        stmt = (
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(desc(UserSession.last_active_at))
        )
        result = await self.session.execute(stmt)
        scalars = result.scalars()
        if asyncio.iscoroutine(scalars):
            scalars = await scalars
        items = scalars.all()
        if asyncio.iscoroutine(items):
            items = await items
        return [i for i in items if isinstance(i, UserSession)] if items else []

    async def delete_by_id(self, session_id: uuid.UUID) -> bool:
        """Удаление конкретной сессии по ID."""
        stmt = delete(UserSession).where(UserSession.id == session_id)
        result = await self.session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        if asyncio.iscoroutine(rowcount):
            rowcount = await rowcount
        return bool(rowcount and rowcount > 0)

    async def delete_by_user_id_except(self, user_id: uuid.UUID, keep_session_id: uuid.UUID) -> int:
        """Удаление всех сессий пользователя кроме указанной (keep_session_id)."""
        stmt = (
            delete(UserSession)
            .where(UserSession.user_id == user_id, UserSession.id != keep_session_id)
        )
        result = await self.session.execute(stmt)
        rowcount = getattr(result, "rowcount", 0)
        if asyncio.iscoroutine(rowcount):
            rowcount = await rowcount
        return int(rowcount) if rowcount else 0

    async def enforce_device_limit(self, user_id: uuid.UUID, max_sessions: int) -> list[UserSession]:
        """
        Контроль лимита устройств (FIFO):
        Если количество активных сессий >= max_sessions,
        удаляет самые старые сессии так, чтобы осталось место для новой сессии (max_sessions - 1).
        Возвращает список удаленных сессий.
        """
        if max_sessions <= 0:
            return []

        active_sessions = await self.list_by_user_id(user_id)
        # Если при добавлении новой сессии их станет больше max_sessions
        excess_count = len(active_sessions) - (max_sessions - 1)
        if excess_count <= 0:
            return []

        # Самые старые сессии находятся в конце списка (так как сортировка desc)
        sessions_to_evict = active_sessions[-excess_count:]
        evicted_ids = [s.id for s in sessions_to_evict]

        if evicted_ids:
            stmt = delete(UserSession).where(UserSession.id.in_(evicted_ids))
            await self.session.execute(stmt)

        return sessions_to_evict

    async def update_activity(
        self,
        session_id: uuid.UUID,
        new_refresh_hash: str | None = None,
        ip_address: str | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        """Обновление времени активности и ротация refresh-токена в сессии."""
        user_session = await self.get_by_id(session_id)
        if user_session:
            user_session.last_active_at = datetime.now(timezone.utc)
            if new_refresh_hash:
                user_session.refresh_token_hash = new_refresh_hash
            if ip_address:
                user_session.ip_address = ip_address
            if expires_at:
                user_session.expires_at = expires_at
            await self.session.flush()
