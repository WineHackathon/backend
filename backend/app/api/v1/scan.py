"""
Пользовательский эндпоинт сканирования винных этикеток (/api/v1/ml/scan).
Включает защиту по X-Device-Fingerprint + IP (лимит 5 сканов для неавторизованных).
"""
import uuid
import logging
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.adapters.database.models.scan_history import UserScanHistory, ScanStatus
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.scan import ScanResultDTO
from application.exceptions.domain_exceptions import WineNotFound
from application.services.catalog_service import CatalogService
from backend.app.config import settings
from backend.app.dependencies import get_optional_user_id, get_rate_limiter, get_ml_dispatcher
from backend.app.services.rate_limiter import ScanRateLimiter
from backend.app.services.ml_dispatcher import MLDispatcher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ml", tags=["Сканирование этикеток"])


@router.post("/scan", response_model=ScanResultDTO, summary="Сканирование этикетки вина (фото бутылки)")
async def scan_wine_label(
    request: Request,
    image: UploadFile = File(..., description="Фотография этикетки или бутылки"),
    device_fingerprint: str | None = Form(None, description="Отпечаток устройства для гостей (для привязки истории)"),
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
    rate_limiter: ScanRateLimiter = Depends(get_rate_limiter),
    ml_dispatcher: MLDispatcher = Depends(get_ml_dispatcher),
    session: AsyncSession = Depends(get_session),
):
    """
    Пользовательский эндпоинт сканирования:
    1. Проверка формата и размера изображения.
    2. Для неавторизованных: проверка фингерпринта и IP (максимум 5 бесплатных сканирований).
    3. При превышении квоты возвращает требование регистрации (registration_required: true).
    4. Распознает вино через ML-слой, подтягивает карточку из каталога.
    5. Сохраняет историю сканирования в базу данных.
    """
    x_device_fingerprint = device_fingerprint or request.headers.get("x-device-fingerprint")
    # Валидация формата файла
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type and image.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Поддерживаются только форматы JPEG, PNG и WebP.",
        )

    # Валидация размера файла
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    image_bytes = await image.read()
    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Размер файла превышает допустимый лимит {settings.max_upload_size_mb} МБ.",
        )

    client_ip = request.client.host if request.client else None
    remaining_scans = None
    registration_required = False

    # 1. Проверка лимита для неавторизованного пользователя
    if not user_id:
        allowed, remaining = await rate_limiter.check_and_increment(
            fingerprint=x_device_fingerprint,
            ip_address=client_ip,
        )
        remaining_scans = remaining
        if not allowed:
            return ScanResultDTO(
                image_id=str(uuid.uuid4()),
                slug=None,
                confidence=None,
                latency_ms=None,
                wine=None,
                remaining_scans=0,
                registration_required=True,
            )

    # 2. Инференс модели
    image_id = str(uuid.uuid4())
    predicted_slug, confidence, latency_ms = await ml_dispatcher.predict(image_bytes, image_id=image_id)

    # 3. Поиск карточки вина в каталоге
    wine_dto = None
    if predicted_slug:
        catalog_service = CatalogService(session)
        try:
            wine_dto = await catalog_service.get_by_slug(predicted_slug)
        except WineNotFound:
            logger.info(f"Вино со слагом {predicted_slug} не найдено в каталоге")
            wine_dto = None
        except Exception as exc:
            logger.warning(f"Ошибка при получении карточки вина {predicted_slug}: {exc}")
            wine_dto = None

    # 4. Сохранение записи в историю сканирований (UserScanHistory)
    scan_repo = ScanRepository(session)
    tm = TransactionManager(session)
    scan_record = UserScanHistory(
        user_id=user_id,
        image_id=image_id,
        image_s3_key=f"scans/{image_id}.jpg",
        predicted_slug=predicted_slug,
        confidence=confidence,
        latency_ms=latency_ms,
        device_fingerprint=x_device_fingerprint,
        ip_address=client_ip,
        status=ScanStatus.SUCCESS if predicted_slug else ScanStatus.FAILED,
    )
    async with tm:
        await scan_repo.save(scan_record)

    return ScanResultDTO(
        image_id=image_id,
        slug=predicted_slug,
        confidence=confidence,
        latency_ms=latency_ms,
        wine=wine_dto,
        remaining_scans=remaining_scans,
        registration_required=registration_required,
    )
