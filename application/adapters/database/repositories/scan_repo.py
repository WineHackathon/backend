"""
Репозиторий для сохранения и выборки истории сканирований винных этикеток.
"""
import uuid
from typing import Sequence
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.scan_history import UserScanHistory


class ScanRepository:
    """Репозиторий истории сканирований."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, scan: UserScanHistory) -> UserScanHistory:
        """Сохранение записи о сканировании."""
        self.session.add(scan)
        await self.session.flush()
        return scan

    async def get_user_scans(self, user_id: uuid.UUID, limit: int = 20) -> Sequence[UserScanHistory]:
        """Получение истории сканирований конкретного пользователя."""
        stmt = (
            select(UserScanHistory)
            .where(UserScanHistory.user_id == user_id)
            .order_by(UserScanHistory.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_fingerprint_scan_count(self, fingerprint: str) -> int:
        """Получение общего числа сканирований для фингерпринта устройства."""
        stmt = select(func.count(UserScanHistory.id)).where(
            UserScanHistory.device_fingerprint == fingerprint
        )
        res = await self.session.scalar(stmt)
        return res or 0
