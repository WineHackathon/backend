"""
Репозиторий для работы с каталогом вин и вкусовой матрицей (Taste Matrix).
"""
import uuid
from typing import Sequence
from sqlalchemy import select, func, distinct, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from application.adapters.database.models.wine import Wine


def escape_like_pattern(term: str) -> str:
    r"""Экранирование спецсимволов %, _, \ для предотвращения LIKE-инъекций."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class WineRepository:
    """Репозиторий каталога вин."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save(self, wine: Wine) -> Wine:
        """Сохранение или обновление сущности вина."""
        self.session.add(wine)
        await self.session.flush()
        return wine

    async def get_by_id(self, wine_id: uuid.UUID) -> Wine | None:
        """Поиск вина по UUID."""
        stmt = (
            select(Wine)
            .where(Wine.id == wine_id)
            .options(selectinload(Wine.pairings))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Wine | None:
        """Поиск вина по уникальному слагу."""
        stmt = (
            select(Wine)
            .where(Wine.slug == slug)
            .options(selectinload(Wine.pairings))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

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
    ) -> tuple[Sequence[Wine], int]:
        """Фильтрованный постраничный поиск вин в каталоге."""
        stmt = select(Wine).options(selectinload(Wine.pairings))
        count_stmt = select(func.count(Wine.id))

        filters = []
        if category:
            escaped = escape_like_pattern(category)
            filters.append(Wine.category.ilike(f"%{escaped}%", escape="\\"))
        if region:
            escaped = escape_like_pattern(region)
            filters.append(Wine.region.ilike(f"%{escaped}%", escape="\\"))
        if winery:
            escaped = escape_like_pattern(winery)
            filters.append(Wine.winery.ilike(f"%{escaped}%", escape="\\"))
        if sugar_type:
            escaped = escape_like_pattern(sugar_type)
            filters.append(Wine.sugar_type.ilike(f"%{escaped}%", escape="\\"))
        if min_score is not None:
            filters.append(Wine.roskachestvo_score >= min_score)
        if query:
            escaped = escape_like_pattern(query)
            pattern = f"%{escaped}%"
            filters.append(
                or_(
                    Wine.name.ilike(pattern, escape="\\"),
                    Wine.winery.ilike(pattern, escape="\\"),
                    Wine.description.ilike(pattern, escape="\\"),
                )
            )

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        stmt = (
            stmt
            .order_by(Wine.roskachestvo_score.desc().nullslast(), Wine.name.asc())
            .offset(offset)
            .limit(limit)
        )

        total = await self.session.scalar(count_stmt) or 0
        res = await self.session.execute(stmt)
        return res.scalars().all(), total

    async def list_regions(self) -> list[str]:
        """Получение списка уникальных регионов производства."""
        stmt = (
            select(distinct(Wine.region))
            .where(Wine.region.isnot(None))
            .order_by(Wine.region)
        )
        res = await self.session.execute(stmt)
        return [r for r in res.scalars().all() if r]

    async def find_by_taste_matrix(
        self,
        category: str | None = None,
        target_sweetness: float | None = None,
        target_body: float | None = None,
        target_acidity: float | None = None,
        target_oak: float | None = None,
        limit: int = 10,
    ) -> Sequence[Wine]:
        """
        Поиск вин, наиболее близких по евклидову расстоянию в 4D-пространстве вкуса:
        (sweetness, body, acidity, oak).
        """
        stmt = select(Wine).options(selectinload(Wine.pairings))
        if category:
            stmt = stmt.where(Wine.category.ilike(f"%{escape_like_pattern(category)}%", escape="\\"))

        # Выбираем вина с заполненной вкусовой матрицей, отдавая приоритет качественным винам с оценкой
        stmt = (
            stmt.where(
                Wine.sweetness.isnot(None),
                Wine.body.isnot(None),
                Wine.acidity.isnot(None),
            )
            .order_by(Wine.roskachestvo_score.desc().nullslast())
            .limit(max(limit * 5, 50))
        )

        res = await self.session.execute(stmt)
        candidates = list(res.scalars().all())

        if not candidates:
            # Fallback к популярным винам категории
            fallback_stmt = (
                select(Wine)
                .options(selectinload(Wine.pairings))
                .order_by(Wine.roskachestvo_score.desc().nullslast())
                .limit(limit)
            )
            if category:
                fallback_stmt = fallback_stmt.where(Wine.category.ilike(f"%{escape_like_pattern(category)}%", escape="\\"))
            fb_res = await self.session.execute(fallback_stmt)
            return fb_res.scalars().all()

        # Расчет евклидова расстояния в Python (безопасно и быстро для пула кандидатов)
        def taste_distance(w: Wine) -> float:
            dist_sq = 0.0
            if target_sweetness is not None and w.sweetness is not None:
                dist_sq += (w.sweetness - target_sweetness) ** 2
            if target_body is not None and w.body is not None:
                dist_sq += (w.body - target_body) ** 2
            if target_acidity is not None and w.acidity is not None:
                dist_sq += (w.acidity - target_acidity) ** 2
            if target_oak is not None and w.oak is not None:
                dist_sq += (w.oak - target_oak) ** 2
            return dist_sq

        candidates.sort(key=taste_distance)
        return candidates[:limit]

    async def find_recommended_wines(
        self,
        intent: "WineSearchIntent",
        limit: int = 3,
    ) -> Sequence[Wine]:
        """
        Умный многокритериальный подбор вин на основе извлеченных намерений (intent):
        - Категория (Красное, Белое и т.д.)
        - Тип сахара (Сухое, Полусухое и т.д.)
        - Гастрономическая пара (стейк, рыба, сыр через WineFoodPairing и описание)
        - Сорт винограда и регион
        - Вкусовой профиль (тело/плотность, сладость, кислотность, дуб)
        - Максимальный бюджет
        - Ранжирование по релевантности и оценке Роскачества
        """
        from application.adapters.database.models.pairing import WineFoodPairing, FoodCategory

        stmt = select(Wine).options(selectinload(Wine.pairings))
        filters = []

        # 1. Фильтр по категории
        if intent.category:
            filters.append(Wine.category == intent.category)

        # 2. Фильтр по типу сахара
        if intent.sugar_type:
            filters.append(Wine.sugar_type.ilike(f"%{escape_like_pattern(intent.sugar_type)}%", escape="\\"))

        # 3. Фильтр по региону
        if intent.region:
            filters.append(Wine.region.ilike(f"%{escape_like_pattern(intent.region)}%", escape="\\"))

        # 4. Фильтр по бюджету (если указан)
        if intent.max_price_rub:
            filters.append(or_(Wine.price_rub <= intent.max_price_rub, Wine.price_rub.is_(None)))

        # 5. Фильтр по сорту винограда
        if intent.grape_variety:
            escaped_grape = escape_like_pattern(intent.grape_variety)
            filters.append(
                or_(
                    Wine.name.ilike(f"%{escaped_grape}%", escape="\\"),
                    Wine.description.ilike(f"%{escaped_grape}%", escape="\\"),
                )
            )

        # 6. Фильтр по гастропаре (через связанные pairings или описание)
        if intent.food_pairing:
            food_cat_map = {
                "мясо / стейк": FoodCategory.MEAT,
                "рыба / морепродукты": [FoodCategory.FISH, FoodCategory.SEAFOOD],
                "сыры": FoodCategory.CHEESE,
                "птица": FoodCategory.POULTRY,
                "десерты": FoodCategory.DESSERT,
                "паста / пицца": FoodCategory.PASTA_PIZZA,
            }
            mapped = food_cat_map.get(intent.food_pairing)
            pairing_subqueries = []
            if mapped:
                if isinstance(mapped, list):
                    pairing_subqueries.append(
                        select(WineFoodPairing.wine_id).where(WineFoodPairing.food_category.in_(mapped))
                    )
                else:
                    pairing_subqueries.append(
                        select(WineFoodPairing.wine_id).where(WineFoodPairing.food_category == mapped)
                    )

            food_kw = intent.food_pairing.split("/")[0].strip()
            desc_filter = Wine.description.ilike(f"%{escape_like_pattern(food_kw)}%", escape="\\")

            if pairing_subqueries:
                filters.append(or_(Wine.id.in_(pairing_subqueries[0]), desc_filter))
            else:
                filters.append(desc_filter)

        strict_stmt = stmt
        if filters:
            strict_stmt = strict_stmt.where(*filters)

        strict_stmt = (
            strict_stmt
            .order_by(Wine.roskachestvo_score.desc().nullslast())
            .limit(max(limit * 5, 20))
        )
        res = await self.session.execute(strict_stmt)
        candidates = list(res.scalars().all())

        # Если строгий запрос дал недостаточно кандидатов, расслабляем фильтры (оставляем только категорию)
        if len(candidates) < limit and intent.category:
            fallback_stmt = (
                select(Wine)
                .options(selectinload(Wine.pairings))
                .where(Wine.category == intent.category)
                .order_by(Wine.roskachestvo_score.desc().nullslast())
                .limit(limit * 5)
            )
            fb_res = await self.session.execute(fallback_stmt)
            for w in fb_res.scalars().all():
                if w not in candidates:
                    candidates.append(w)
                if len(candidates) >= limit * 5:
                    break

        if not candidates:
            # Абсолютный fallback: топ вин каталога
            top_stmt = (
                select(Wine)
                .options(selectinload(Wine.pairings))
                .order_by(Wine.roskachestvo_score.desc().nullslast())
                .limit(limit)
            )
            top_res = await self.session.execute(top_stmt)
            return top_res.scalars().all()

        # Если задан target_body или вкусовая матрица — сортируем кандидатов по евклидову расстоянию вкуса
        if (
            intent.target_body is not None
            or intent.target_sweetness is not None
            or intent.target_acidity is not None
            or intent.target_oak is not None
        ):
            def score_candidate(w: Wine) -> float:
                dist = 0.0
                if intent.target_body is not None and w.body is not None:
                    dist += (w.body - intent.target_body) ** 2
                if intent.target_sweetness is not None and w.sweetness is not None:
                    dist += (w.sweetness - intent.target_sweetness) ** 2
                if intent.target_acidity is not None and w.acidity is not None:
                    dist += (w.acidity - intent.target_acidity) ** 2
                if intent.target_oak is not None and w.oak is not None:
                    dist += (w.oak - intent.target_oak) ** 2
                quality_bonus = (w.roskachestvo_score or 70.0) / 100.0
                return dist - (quality_bonus * 2.0)

            candidates.sort(key=score_candidate)

        return candidates[:limit]

