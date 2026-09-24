"""
Эндпоинты каталога вин и вкусовой матрицы (/api/v1/catalog).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.wine import WineDetailDTO, WineDTO, PaginatedWinesDTO, WineFilterDTO
from application.services.catalog_service import CatalogService

router = APIRouter(prefix="/api/v1/catalog", tags=["Каталог вин"])


@router.get(
    "/wines",
    response_model=PaginatedWinesDTO,
    summary="Поиск и фильтрация вин в каталоге",
)
async def list_wines(
    category: str | None = Query(None, description="Категория вина (Красное, Белое, Розовое, Игристое)"),
    region: str | None = Query(None, description="Регион"),
    winery: str | None = Query(None, description="Винодельня"),
    sugar_type: str | None = Query(None, description="Содержание сахара"),
    min_score: float | None = Query(None, description="Минимальный рейтинг Роскачества"),
    query: str | None = Query(None, description="Поисковый запрос"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    limit: int = Query(50, ge=1, le=100, description="Лимит на страницу"),
    session: AsyncSession = Depends(get_session),
):
    """Полнотекстовый поиск и многофакторная фильтрация каталога российских вин."""
    service = CatalogService(session)
    filter_dto = WineFilterDTO(
        category=category,
        region=region,
        winery=winery,
        sugar_type=sugar_type,
        min_score=min_score,
        query=query,
        offset=offset,
        limit=limit,
    )
    return await service.list_wines(filter_dto)


@router.get(
    "/wines/{id_or_slug}/similar",
    response_model=list[WineDTO],
    summary="Поиск похожих вин по 4D вкусовой матрице",
)
async def get_similar_wines(
    id_or_slug: str,
    limit: int = Query(4, ge=1, le=20, description="Количество похожих вин"),
    session: AsyncSession = Depends(get_session),
):
    """Рекомендация похожих вин на основе евклидова расстояния в 4D вкусовом пространстве."""
    service = CatalogService(session)
    return await service.find_similar_wines(id_or_slug, limit=limit)


@router.get(
    "/wines/{id_or_slug}",
    response_model=WineDetailDTO,
    summary="Получить подробную карточку вина по ID или слагу",
)
async def get_wine_by_id_or_slug(
    id_or_slug: str,
    session: AsyncSession = Depends(get_session),
):
    """Получение подробной карточки вина с дегустационными заметками и гастропарами (по UUID или слагу)."""
    service = CatalogService(session)
    return await service.get_by_id_or_slug(id_or_slug)
