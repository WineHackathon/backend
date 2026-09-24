"""
Репозиторий для работы с каталогом вин и вкусовой матрицей (Taste Matrix).
"""
import uuid
from typing import TYPE_CHECKING, Sequence
from sqlalchemy import select, func, distinct, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from application.adapters.database.models.wine import Wine
from application.adapters.database.models.pairing import WineFoodPairing, FoodCategory

if TYPE_CHECKING:
    from application.dto.wine_intent import WineSearchIntent


def escape_like_pattern(term: str) -> str:
    r"""Экранирование спецсимволов %, _, \ для предотвращения LIKE-инъекций."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def calculate_taste_distance(
    wine: Wine,
    target_sweetness: float | None = None,
    target_body: float | None = None,
    target_acidity: float | None = None,
    target_oak: float | None = None,
) -> float:
    """
    Расчет квадрата евклидова расстояния вина до целевых координат в 4D-пространстве вкуса:
    (sweetness, body, acidity, oak).
    """
    dist_sq = 0.0
    if target_sweetness is not None and wine.sweetness is not None:
        dist_sq += (wine.sweetness - target_sweetness) ** 2
    if target_body is not None and wine.body is not None:
        dist_sq += (wine.body - target_body) ** 2
    if target_acidity is not None and wine.acidity is not None:
        dist_sq += (wine.acidity - target_acidity) ** 2
    if target_oak is not None and wine.oak is not None:
        dist_sq += (wine.oak - target_oak) ** 2
    return dist_sq


class WineRepository:
    """Репозиторий каталога вин."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # 1. Базовые CRUD и выборки по ключам
    # =========================================================================

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
        """Поиск вина по уникальному слагу (с нормализацией пробелов)."""
        clean_slug = slug.strip()
        stmt = (
            select(Wine)
            .where(Wine.slug == clean_slug)
            .options(selectinload(Wine.pairings))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    # =========================================================================
    # 2. Поиск и фильтрация каталога
    # =========================================================================

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
        """Фильтрованный постраничный поиск вин в каталоге с Early Return."""
        filters = self._build_catalog_filters(
            category=category,
            region=region,
            winery=winery,
            sugar_type=sugar_type,
            min_score=min_score,
            query=query,
        )

        count_stmt = select(func.count(Wine.id))
        if filters:
            count_stmt = count_stmt.where(*filters)

        total = await self.session.scalar(count_stmt) or 0
        if total == 0:
            return [], 0

        stmt = (
            select(Wine)
            .options(selectinload(Wine.pairings))
            .order_by(Wine.roskachestvo_score.desc().nullslast(), Wine.name.asc())
            .offset(offset)
            .limit(limit)
        )
        if filters:
            stmt = stmt.where(*filters)

        res = await self.session.execute(stmt)
        return res.scalars().all(), total

    @staticmethod
    def _is_sparkling_category(category: str | None) -> bool:
        if not category:
            return False
        cat = category.lower().strip()
        return "игрист" in cat or "шампан" in cat

    @staticmethod
    def _sparkling_condition():
        return or_(
            Wine.category == "Игристое",
            Wine.sugar_type.in_(["Брют", "Экстра брют"]),
            func.lower(Wine.name).like("%игрист%"),
            func.lower(Wine.name).like("%брют%"),
            func.lower(Wine.name).like("%шампан%"),
            func.lower(Wine.description).like("%игристое вино%"),
            func.lower(Wine.description).like("%игристых вин%"),
        )

    def _build_catalog_filters(
        self,
        category: str | None = None,
        region: str | None = None,
        winery: str | None = None,
        sugar_type: str | None = None,
        min_score: float | None = None,
        query: str | None = None,
    ) -> list:
        """Построение условий фильтрации для каталога (ANSI SQL, без ворнингов IDE)."""
        filters = []
        if category:
            if self._is_sparkling_category(category):
                filters.append(self._sparkling_condition())
            else:
                escaped = escape_like_pattern(category).lower()
                filters.append(func.lower(Wine.category).like(f"%{escaped}%", escape="\\"))
        if region:
            escaped = escape_like_pattern(region).lower()
            filters.append(func.lower(Wine.region).like(f"%{escaped}%", escape="\\"))
        if winery:
            escaped = escape_like_pattern(winery).lower()
            filters.append(func.lower(Wine.winery).like(f"%{escaped}%", escape="\\"))
        if sugar_type:
            escaped = escape_like_pattern(sugar_type).lower()
            filters.append(func.lower(Wine.sugar_type).like(f"%{escaped}%", escape="\\"))
        if min_score is not None:
            filters.append(Wine.roskachestvo_score >= min_score)
        if query:
            escaped = escape_like_pattern(query).lower()
            pattern = f"%{escaped}%"
            filters.append(
                or_(
                    func.lower(Wine.name).like(pattern, escape="\\"),
                    func.lower(Wine.winery).like(pattern, escape="\\"),
                    func.lower(Wine.description).like(pattern, escape="\\"),
                )
            )
        return filters

    async def list_regions(self) -> list[str]:
        """Получение списка уникальных регионов производства."""
        stmt = (
            select(distinct(Wine.region))
            .where(Wine.region.isnot(None))
            .order_by(Wine.region)
        )
        res = await self.session.execute(stmt)
        return [r for r in res.scalars().all() if r]

    # =========================================================================
    # 3. Подбор по Вкусовой Матрице (Taste Matrix)
    # =========================================================================

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
            if self._is_sparkling_category(category):
                stmt = stmt.where(self._sparkling_condition())
            else:
                escaped = escape_like_pattern(category).lower()
                stmt = stmt.where(func.lower(Wine.category).like(f"%{escaped}%", escape="\\"))

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
            return await self._fetch_fallback_wines(category=category, limit=limit, existing_wines=[])

        candidates.sort(
            key=lambda w: calculate_taste_distance(
                w,
                target_sweetness=target_sweetness,
                target_body=target_body,
                target_acidity=target_acidity,
                target_oak=target_oak,
            )
        )
        return candidates[:limit]

    # =========================================================================
    # 4. Умный рекомендательный движок по намерениям (Intent-Based Search)
    # =========================================================================

    async def find_recommended_wines(
        self,
        intent: "WineSearchIntent",
        limit: int = 3,
    ) -> Sequence[Wine]:
        """
        Умный многокритериальный подбор вин на основе извлеченных намерений (intent).
        Оркестрирует фильтрацию, многоуровневый fallback и ранжирование кандидатов.
        """
        stmt = select(Wine).options(selectinload(Wine.pairings))
        filters = self._build_intent_filters(intent)

        if filters:
            stmt = stmt.where(*filters)

        strict_stmt = (
            stmt
            .order_by(Wine.roskachestvo_score.desc().nullslast())
            .limit(max(limit * 5, 20))
        )
        res = await self.session.execute(strict_stmt)
        candidates = list(res.scalars().all())

        # Graceful degradation: если строгий запрос вернул недостаточно вин
        if len(candidates) < limit and intent.category:
            fallback = await self._fetch_fallback_wines(
                category=intent.category,
                limit=limit * 5,
                existing_wines=candidates,
            )
            for w in fallback:
                if w not in candidates:
                    candidates.append(w)
                if len(candidates) >= limit * 5:
                    break

        if not candidates:
            # Абсолютный fallback: топ вин каталога
            fallback_top = await self._fetch_fallback_wines(
                category=None,
                limit=limit,
                existing_wines=[],
            )
            return fallback_top

        # Ранжирование кандидатов с учетом вкусовой близости и оценки качества
        return self._rank_by_taste_and_quality(candidates, intent, limit)

    # -------------------------------------------------------------------------
    # Вспомогательные декомпозированные методы рекомендаций
    # -------------------------------------------------------------------------

    def _build_intent_filters(self, intent: "WineSearchIntent") -> list:
        """Построение списка предикатов фильтрации по намерениям пользователя."""
        filters = []

        if intent.category:
            if self._is_sparkling_category(intent.category):
                filters.append(self._sparkling_condition())
            else:
                filters.append(Wine.category == intent.category)

        if intent.sugar_type:
            escaped_sugar = escape_like_pattern(intent.sugar_type).lower()
            if "брют" in escaped_sugar:
                filters.append(
                    or_(
                        func.lower(Wine.sugar_type).like(f"%{escaped_sugar}%", escape="\\"),
                        func.lower(Wine.name).like(f"%{escaped_sugar}%", escape="\\"),
                    )
                )
            else:
                filters.append(func.lower(Wine.sugar_type).like(f"%{escaped_sugar}%", escape="\\"))

        if intent.region:
            escaped_reg = escape_like_pattern(intent.region).lower()
            filters.append(func.lower(Wine.region).like(f"%{escaped_reg}%", escape="\\"))

        if intent.max_price_rub:
            filters.append(or_(Wine.price_rub <= intent.max_price_rub, Wine.price_rub.is_(None)))

        if intent.grape_variety:
            escaped_grape = escape_like_pattern(intent.grape_variety).lower()
            pattern = f"%{escaped_grape}%"
            filters.append(
                or_(
                    func.lower(Wine.name).like(pattern, escape="\\"),
                    func.lower(Wine.description).like(pattern, escape="\\"),
                )
            )

        if intent.food_pairing:
            food_condition = self._build_food_pairing_condition(intent.food_pairing)
            if food_condition is not None:
                filters.append(food_condition)

        return filters

    def _build_food_pairing_condition(self, food_pairing: str):
        """Формирование условия поиска по гастрономической паре."""
        food_cat_map = {
            "мясо / стейк": FoodCategory.MEAT,
            "рыба / морепродукты": [FoodCategory.FISH, FoodCategory.SEAFOOD],
            "сыры": FoodCategory.CHEESE,
            "птица": FoodCategory.POULTRY,
            "десерты": FoodCategory.DESSERT,
            "паста / пицца": FoodCategory.PASTA_PIZZA,
        }
        key = food_pairing.lower().strip()
        mapped = food_cat_map.get(key)

        food_kw = key.split("/")[0].strip()
        escaped_food = escape_like_pattern(food_kw).lower()
        desc_filter = func.lower(Wine.description).like(f"%{escaped_food}%", escape="\\")

        if mapped:
            pairing_filter = (
                WineFoodPairing.food_category.in_(mapped)
                if isinstance(mapped, list)
                else (WineFoodPairing.food_category == mapped)
            )
            subquery = select(WineFoodPairing.wine_id).where(pairing_filter)
            return or_(Wine.id.in_(subquery), desc_filter)

        return desc_filter

    async def _fetch_fallback_wines(
        self,
        category: str | None,
        limit: int,
        existing_wines: list[Wine],
    ) -> list[Wine]:
        """Многоуровневый fallback: топ вин категории или топ всего каталога."""
        stmt = (
            select(Wine)
            .options(selectinload(Wine.pairings))
            .order_by(Wine.roskachestvo_score.desc().nullslast())
            .limit(limit)
        )
        if category:
            if self._is_sparkling_category(category):
                stmt = stmt.where(self._sparkling_condition())
            else:
                escaped_cat = escape_like_pattern(category).lower()
                stmt = stmt.where(func.lower(Wine.category).like(f"%{escaped_cat}%", escape="\\"))

        res = await self.session.execute(stmt)
        wines = list(res.scalars().all())

        if not wines and category:
            # Абсолютный fallback: топ каталога без фильтра категории
            top_stmt = (
                select(Wine)
                .options(selectinload(Wine.pairings))
                .order_by(Wine.roskachestvo_score.desc().nullslast())
                .limit(limit)
            )
            top_res = await self.session.execute(top_stmt)
            wines = list(top_res.scalars().all())

        return wines

    def _rank_by_taste_and_quality(
        self,
        candidates: list[Wine],
        intent: "WineSearchIntent",
        limit: int,
    ) -> list[Wine]:
        """Ранжирование кандидатов по близости вкусовых координат с бонусом за оценку Роскачества."""
        has_taste_target = any(
            t is not None
            for t in [intent.target_body, intent.target_sweetness, intent.target_acidity, intent.target_oak]
        )

        if not has_taste_target:
            return candidates[:limit]

        def score_candidate(w: Wine) -> float:
            dist = calculate_taste_distance(
                w,
                target_sweetness=intent.target_sweetness,
                target_body=intent.target_body,
                target_acidity=intent.target_acidity,
                target_oak=intent.target_oak,
            )
            quality_bonus = (w.roskachestvo_score or 70.0) / 100.0
            return dist - (quality_bonus * 2.0)

        candidates.sort(key=score_candidate)
        return candidates[:limit]
