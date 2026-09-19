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

        # Выбираем вина с заполненной вкусовой матрицей
        stmt = stmt.where(
            Wine.sweetness.isnot(None),
            Wine.body.isnot(None),
            Wine.acidity.isnot(None),
        ).limit(limit * 3)

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
