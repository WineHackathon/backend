"""
Прикладной сервис обработки результатов сканирования винных этикеток.
"""
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.scan_history import UserScanHistory, ScanStatus
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.wine import WineDTO
from application.exceptions.domain_exceptions import WineNotFound
from application.services.catalog_service import CatalogService

logger = logging.getLogger(__name__)


class ScanService:
    """Сервис обработки сканирований и сохранения истории распознавания."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.scan_repo = ScanRepository(session)
        self.catalog_service = CatalogService(session)
        self.tm = TransactionManager(session)

    async def get_wine_by_slug_safe(self, slug: str | None) -> WineDTO | None:
        """Безопасное получение карточки вина по слагу без выброса исключений при отсутствии."""
        if not slug:
            return None
        try:
            return await self.catalog_service.get_by_slug(slug)
        except WineNotFound:
            logger.info("Вино со слагом %s не найдено в каталоге", slug)
            return None
        except Exception as exc:
            logger.warning("Ошибка при получении карточки вина %s: %s", slug, exc)
            return None

    async def record_scan(
        self,
        image_id: str,
        predicted_slug: str | None,
        confidence: float | None = None,
        latency_ms: int | None = None,
        user_id: uuid.UUID | None = None,
        device_fingerprint: str | None = None,
        ip_address: str | None = None,
    ) -> UserScanHistory:
        """Сохранение записи в историю сканирований (UserScanHistory)."""
        scan_record = UserScanHistory(
            id=uuid.uuid4(),
            user_id=user_id,
            image_id=image_id,
            image_s3_key=f"scans/{image_id}.jpg",
            predicted_slug=predicted_slug,
            confidence=confidence,
            latency_ms=latency_ms,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            status=ScanStatus.SUCCESS if predicted_slug else ScanStatus.FAILED,
        )
        async with self.tm:
            await self.scan_repo.save(scan_record)

        return scan_record
