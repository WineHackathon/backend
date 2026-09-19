"""
Прикладной сервис каталога вин и вкусовой матрицы.
"""
import uuid
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.repositories.wine_repo import WineRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.wine import WineDTO, WineDetailDTO, FoodPairingDTO
from application.exceptions.domain_exceptions import WineNotFound


class CatalogService:
    """Сервис бизнес-логики каталога вин."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WineRepository(session)
        self.tm = TransactionManager(session)

    @staticmethod
    def to_dto(wine) -> WineDTO:
        """Преобразование модели Wine в компактный WineDTO."""
        return WineDTO(
            id=wine.id,
            slug=wine.slug,
            name=wine.name,
            category=wine.category,
            color_desc=wine.color_desc,
            region=wine.region,
            grape_varieties=wine.grape_varieties or [],
            winery=wine.winery,
            roskachestvo_score=wine.roskachestvo_score,
            sugar_type=wine.sugar_type,
            price_rub=wine.price_rub,
            image_s3_key=wine.image_s3_key,
            image_url=f"/s3/catalog/{wine.image_s3_key}" if wine.image_s3_key else None,
            sweetness=wine.sweetness,
            body=wine.body,
            acidity=wine.acidity,
            oak=wine.oak,
        )

    @classmethod
    def to_detail_dto(cls, wine) -> WineDetailDTO:
        """Преобразование модели Wine в полный WineDetailDTO."""
        base_dto = cls.to_dto(wine)
        pairings = [
            FoodPairingDTO(
                id=p.id,
                food_category=p.food_category,
                dish_name=p.dish_name,
                recommendation_reason=p.recommendation_reason,
            )
            for p in (wine.pairings or [])
        ]
        return WineDetailDTO(
            **base_dto.model_dump(),
            description=wine.description,
            vintage_year=wine.vintage_year,
            aroma_tags=wine.aroma_tags or [],
            flavor_tags=wine.flavor_tags or [],
            derived_attributes_confidence=wine.derived_attributes_confidence,
            pairings=pairings,
            created_at=wine.created_at,
        )

    async def get_by_slug(self, slug: str) -> WineDetailDTO:
        """Получение детальной карточки вина по слагу."""
        wine = await self.repo.get_by_slug(slug)
        if not wine:
            raise WineNotFound(slug)
        return self.to_detail_dto(wine)

    async def get_by_id(self, wine_id: uuid.UUID) -> WineDetailDTO:
        """Получение детальной карточки вина по ID."""
        wine = await self.repo.get_by_id(wine_id)
        if not wine:
            raise WineNotFound(str(wine_id))
        return self.to_detail_dto(wine)

    async def list_wines(
        self,
        category: str | None = None,
        region: str | None = None,
        winery: str | None = None,
        sugar_type: str | None = None,
        min_score: float | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> dict:
        """Поиск и фильтрация вин в каталоге."""
        items, total = await self.repo.list_wines(
            category=category,
            region=region,
            winery=winery,
            sugar_type=sugar_type,
            min_score=min_score,
            query=query,
            offset=offset,
            limit=limit,
        )
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [self.to_dto(w) for w in items],
        }

    async def list_regions(self) -> list[str]:
        """Получение всех регионов."""
        return await self.repo.list_regions()

    async def search_by_taste_matrix(
        self,
        category: str | None = None,
        target_sweetness: float | None = None,
        target_body: float | None = None,
        target_acidity: float | None = None,
        target_oak: float | None = None,
        limit: int = 10,
    ) -> list[WineDTO]:
        """Поиск вин по вкусовой матрице (4D расстояние вкуса)."""
        wines = await self.repo.find_by_taste_matrix(
            category=category,
            target_sweetness=target_sweetness,
            target_body=target_body,
            target_acidity=target_acidity,
            target_oak=target_oak,
            limit=limit,
        )
        return [self.to_dto(w) for w in wines]
