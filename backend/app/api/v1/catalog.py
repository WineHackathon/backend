"""
Эндпоинты каталога вин и вкусовой матрицы (/api/v1/catalog).
"""
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.wine import WineDTO, WineDetailDTO, WineFilterDTO, PaginatedWinesDTO
from application.services.catalog_service import CatalogService

router = APIRouter(prefix="/api/v1/catalog", tags=["Wine Catalog"])


@router.get("/wines", response_model=PaginatedWinesDTO, summary="List wines with filtering and taste matrix")
async def list_wines(
    filter_dto: WineFilterDTO = Depends(),
    session: AsyncSession = Depends(get_session),
):
    """Постраничный список вин с поддержкой фильтров и вкусовой матрицы."""
    service = CatalogService(session)
    return await service.list_wines(filter_dto)



@router.get("/wines/{slug}", response_model=WineDetailDTO, summary="Get wine details by slug")
async def get_wine_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
):
    """Получение подробной карточки вина с дегустационными заметками и гастропарами."""
    service = CatalogService(session)
    return await service.get_by_slug(slug)


@router.get("/regions", response_model=list[str], summary="List unique wine regions")
async def list_regions(
    session: AsyncSession = Depends(get_session),
):
    """Список доступных винодельческих регионов."""
    service = CatalogService(session)
    return await service.list_regions()
