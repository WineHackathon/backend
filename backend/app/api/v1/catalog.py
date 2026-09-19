"""
Эндпоинты каталога вин и вкусовой матрицы (/api/v1/catalog).
"""
import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.wine import WineDTO, WineDetailDTO
from application.services.catalog_service import CatalogService

router = APIRouter(prefix="/api/v1/catalog", tags=["Wine Catalog"])


@router.get("/wines", summary="List wines with filtering and taste matrix")
async def list_wines(
    category: str | None = Query(None, description="Категория (Белое, Красное, Розовое, Игристое)"),
    region: str | None = Query(None, description="Регион"),
    winery: str | None = Query(None, description="Производитель"),
    sugar_type: str | None = Query(None, description="Сахар (Сухое, Полусухое и др.)"),
    min_score: float | None = Query(None, description="Минимальный балл Роскачества"),
    query: str | None = Query(None, description="Текстовый поиск по названию/описанию"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Постраничный список вин с поддержкой фильтров и вкусовой матрицы."""
    service = CatalogService(session)
    return await service.list_wines(
        category=category,
        region=region,
        winery=winery,
        sugar_type=sugar_type,
        min_score=min_score,
        query=query,
        offset=offset,
        limit=limit,
    )


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
