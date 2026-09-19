"""
Эндпоинты профиля пользователя, винного погреба и истории сканирований (/api/v1/users).
"""
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.adapters.database.repositories.scan_repo import ScanRepository
from application.dto.user import UserDTO
from application.dto.cellar import CellarItemDTO, CellarItemCreateDTO
from application.dto.scan import ScanHistoryItemDTO
from application.services.user_service import UserService
from application.services.cellar_service import CellarService
from application.services.catalog_service import CatalogService
from backend.app.dependencies import get_current_user_id

router = APIRouter(prefix="/api/v1/users", tags=["User Profile & Cellar"])


@router.get("/me", response_model=UserDTO, summary="Get current authenticated user profile")
async def get_my_profile(
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Получение профиля текущего пользователя, включая вкусовой профиль (taste_profile)."""
    service = UserService(session)
    return await service.get_by_id(user_id)


@router.get("/cellar", response_model=list[CellarItemDTO], summary="List wines in user cellar")
async def get_my_cellar(
    status: str | None = Query(None, description="Статус (in_cellar, wishlist, tasted)"),
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Список вин в личном погребе / вишлисте пользователя."""
    service = CellarService(session)
    return await service.list_items(user_id, status=status)


@router.post("/cellar", response_model=CellarItemDTO, summary="Add wine to cellar or wishlist")
async def add_to_my_cellar(
    dto: CellarItemCreateDTO,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Добавление вина в погреб или вишлист."""
    service = CellarService(session)
    return await service.add_item(user_id, dto)


@router.delete("/cellar/{item_id}", summary="Remove wine from cellar")
async def remove_from_my_cellar(
    item_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Удаление позиции из личного погреба."""
    service = CellarService(session)
    await service.remove_item(user_id, item_id)
    return {"status": "deleted", "item_id": str(item_id)}


@router.get("/scans", response_model=list[ScanHistoryItemDTO], summary="Get user scan history")
async def get_my_scans(
    limit: int = Query(20, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """История сканирований текущего пользователя."""
    repo = ScanRepository(session)
    scans = await repo.get_user_scans(user_id, limit=limit)
    return [
        ScanHistoryItemDTO(
            id=s.id,
            image_id=s.image_id,
            predicted_slug=s.predicted_slug,
            confidence=s.confidence,
            latency_ms=s.latency_ms,
            status=s.status,
            created_at=s.created_at,
        )
        for s in scans
    ]
