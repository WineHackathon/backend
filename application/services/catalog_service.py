"""
Прикладной сервис каталога вин и вкусовой матрицы.
"""
import uuid
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.wine import Wine
from application.adapters.database.repositories.wine_repo import WineRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.wine import (
    WineDTO,
    WineDetailDTO,
    FoodPairingDTO,
    WineFilterDTO,
    TasteMatrixSearchDTO,
    PaginatedWinesDTO,
)
from application.dto.wine_intent import WineSearchIntent
from application.exceptions.domain_exceptions import WineNotFound


class CatalogService:
    """Сервис бизнес-логики каталога вин."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WineRepository(session)
        self.tm = TransactionManager(session)

    @staticmethod
    def to_dto(wine: Wine) -> WineDTO:
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
            image_url=(
                getattr(wine, "image_url", None)
                or (
                    (f"/s3/{wine.image_s3_key.lstrip('/')}" if wine.image_s3_key.lstrip("/").startswith("catalog/") else f"/s3/catalog/{wine.image_s3_key.lstrip('/')}")
                    if wine.image_s3_key
                    else None
                )
            ),
            sweetness=wine.sweetness,
            body=wine.body,
            acidity=wine.acidity,
            oak=wine.oak,
        )

    @classmethod
    def to_detail_dto(cls, wine: Wine) -> WineDetailDTO:
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

    async def get_by_id_or_slug(self, id_or_slug: str) -> WineDetailDTO:
        """Получение детальной карточки вина универсально: по UUID или слагу."""
        wine = None
        # 1. Если передан валидный UUID, сначала ищем по ID
        try:
            val_uuid = uuid.UUID(id_or_slug)
            wine = await self.repo.get_by_id(val_uuid)
        except (ValueError, AttributeError):
            pass

        # 2. Если по UUID не найдено или это текстовый слаг — ищем по slug
        if not wine:
            wine = await self.repo.get_by_slug(id_or_slug)

        if not wine:
            raise WineNotFound(id_or_slug)

        return self.to_detail_dto(wine)

    async def list_wines(
        self,
        filter_dto: WineFilterDTO | None = None,
        **kwargs,
    ) -> PaginatedWinesDTO:
        """Поиск и фильтрация вин в каталоге с возвратом типизированного PaginatedWinesDTO."""
        if filter_dto is None:
            filter_dto = WineFilterDTO(**kwargs)
        elif kwargs:
            filter_dto = filter_dto.model_copy(update=kwargs)

        items, total = await self.repo.list_wines(
            category=filter_dto.category,
            region=filter_dto.region,
            winery=filter_dto.winery,
            sugar_type=filter_dto.sugar_type,
            min_score=filter_dto.min_score,
            query=filter_dto.query,
            offset=filter_dto.offset,
            limit=filter_dto.limit,
        )
        return PaginatedWinesDTO(
            total=total,
            limit=filter_dto.limit,
            offset=filter_dto.offset,
            items=[self.to_dto(w) for w in items],
        )

    async def list_regions(self) -> list[str]:
        """Получение всех регионов."""
        return await self.repo.list_regions()

    async def search_by_taste_matrix(
        self,
        search_dto: TasteMatrixSearchDTO | None = None,
        **kwargs,
    ) -> list[WineDTO]:
        """Поиск вин по вкусовой матрице (4D расстояние вкуса)."""
        if search_dto is None:
            search_dto = TasteMatrixSearchDTO(**kwargs)
        elif kwargs:
            search_dto = search_dto.model_copy(update=kwargs)

        wines = await self.repo.find_by_taste_matrix(
            category=search_dto.category,
            target_sweetness=search_dto.target_sweetness,
            target_body=search_dto.target_body,
            target_acidity=search_dto.target_acidity,
            target_oak=search_dto.target_oak,
            limit=search_dto.limit,
        )
        return [self.to_dto(w) for w in wines]

    async def find_similar_wines(self, slug: str, limit: int = 4) -> list[WineDTO]:
        """Поиск похожих вин по вкусовой матрице (сладость, плотность, кислотность, дуб)."""
        base_wine = await self.repo.get_by_slug(slug)
        if not base_wine:
            return []
        wines = await self.repo.find_by_taste_matrix(
            category=base_wine.category,
            target_sweetness=base_wine.sweetness or 1.2,
            target_body=base_wine.body or 3.0,
            target_acidity=base_wine.acidity or 3.0,
            target_oak=base_wine.oak or 2.0,
            limit=limit + 2,
        )
        return [self.to_dto(w) for w in wines if w.slug != slug][:limit]

    async def recommend_wines_by_intent(self, intent: WineSearchIntent, limit: int = 3) -> list[WineDTO]:
        """Умный многокритериальный подбор вин на основе извлеченных намерений пользователя."""
        wines = await self.repo.find_recommended_wines(intent, limit=limit)
        return [self.to_dto(w) for w in wines]


