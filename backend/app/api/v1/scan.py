"""
Пользовательский эндпоинт сканирования винных этикеток (/api/v1/ml/scan).
Включает защиту по X-Device-Fingerprint + IP (лимит 5 сканов для неавторизованных).
"""
import uuid
from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.adapters.database.models.scan_history import UserScanHistory, ScanStatus
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.scan import ScanResultDTO
from application.services.catalog_service import CatalogService
from backend.app.dependencies import get_optional_user_id, get_rate_limiter, get_ml_dispatcher
from backend.app.services.rate_limiter import ScanRateLimiter
from backend.app.services.ml_dispatcher import MLDispatcher

router = APIRouter(prefix="/api/v1/ml", tags=["Wine Scanner"])


@router.post("/scan", response_model=ScanResultDTO, summary="Scan wine bottle for mobile/web app")
async def scan_wine_label(
    request: Request,
    image: UploadFile = File(..., description="Фотография этикетки или бутылки"),
    x_device_fingerprint: str | None = Header(None, alias="X-Device-Fingerprint"),
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
    rate_limiter: ScanRateLimiter = Depends(get_rate_limiter),
    ml_dispatcher: MLDispatcher = Depends(get_ml_dispatcher),
    session: AsyncSession = Depends(get_session),
):
    """
    Пользовательский эндпоинт сканирования:
    1. Для неавторизованных: проверка фингерпринта и IP (максимум 5 бесплатных сканирований).
    2. При превышении квоты возвращает требование регистрации (registration_required: true).
    3. Распознает вино через ML-слой, подтягивает карточку из каталога.
    4. Сохраняет историю сканирования в базу данных.
    """
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
    image_bytes = await image.read()
    image_id = str(uuid.uuid4())
    predicted_slug, confidence, latency_ms = await ml_dispatcher.predict(image_bytes, image_id=image_id)

    # 3. Поиск карточки вина в каталоге
    wine_dto = None
    if predicted_slug:
        catalog_service = CatalogService(session)
        try:
            detail = await catalog_service.get_by_slug(predicted_slug)
            wine_dto = detail
        except Exception:
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
