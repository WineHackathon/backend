"""
Эндпоинты каталога вин и вкусовой матрицы (/api/v1/catalog).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.wine import WineDetailDTO
from application.services.catalog_service import CatalogService

router = APIRouter(prefix="/api/v1/catalog", tags=["Детали вина"])


@router.get("/wines/{slug}", response_model=WineDetailDTO, summary="Получить подробную карточку вина по слагу")
async def get_wine_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
):
    """Получение подробной карточки вина с дегустационными заметками и гастропарами."""
    service = CatalogService(session)
    return await service.get_by_slug(slug)

