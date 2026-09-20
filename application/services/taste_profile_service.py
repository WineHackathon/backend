"""
Прикладной сервис фоновой агрегации вкусового профиля пользователя (Taste Profile).
Сохраняет сырые данные диалога и обновляет экспоненциальное скользящее среднее (EMA) вкусов.
"""
import logging
import uuid
from typing import Any, Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.preference_history import UserPreferenceHistory
from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.repositories.preference_repo import PreferenceRepository
from application.adapters.database.transaction_manager import TransactionManager
from application.dto.user import TasteProfileDTO, PreferenceSessionCreateDTO

logger = logging.getLogger(__name__)


def _parse_scale_value(val: Any, keyword_map: dict[str, float], default: float | None = None) -> float | None:
    """
    Безопасное извлечение числовой шкалы вкуса (1.0 - 5.0).
    Поддерживает как явные числа (float/int), так и текстовые ключевые слова.
    """
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return max(1.0, min(5.0, float(val)))
    if isinstance(val, str):
        val_lower = val.lower().strip()
        for kw, score in keyword_map.items():
            if kw in val_lower:
                return score
    return default


def _extract_aromas(val: Any) -> list[str]:
    """
    Безопасное извлечение списка ароматов из строк, списков, кортежей или множеств.
    Полностью защищено от AttributeError при передаче list вместо str.
    """
    if not val:
        return []
    if isinstance(val, (list, set, tuple)):
        return [str(item).strip().lower() for item in val if str(item).strip()]
    if isinstance(val, str):
        items: list[str] = []
        for part in val.replace(";", ",").split(","):
            cleaned = part.strip().lower()
            if cleaned:
                items.append(cleaned)
        return items
    return []


def _calculate_ema(curr: float | None, new_val: float | None, default: float, alpha: float = 0.35) -> float:
    """Расчет экспоненциального скользящего среднего (EMA) с округлением до 2 знаков."""
    if new_val is None:
        return curr if curr is not None else default
    if curr is None:
        return round(new_val, 2)
    return round(curr * (1.0 - alpha) + new_val * alpha, 2)


class TasteProfileService:
    """Сервис обновления и агрегации вкусового профиля пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.pref_repo = PreferenceRepository(session)
        self.tm = TransactionManager(session)

    async def record_preferences_and_update_profile(
        self,
        dto: PreferenceSessionCreateDTO | None = None,
        **kwargs: Any,
    ) -> TasteProfileDTO | None:
        """
        Фоновая задача обновления вкусового профиля:
        1. Сохранение сырой истории диалога в UserPreferenceHistory.
        2. Агрегация вкусового профиля авторизованного пользователя (User.taste_profile) через EMA.
        """
        if dto is None:
            dto = PreferenceSessionCreateDTO(**kwargs)
        elif kwargs:
            dto = dto.model_copy(update=kwargs)

        # 1. Сохранение сырой истории
        pref_record = UserPreferenceHistory(
            user_id=dto.user_id,
            session_id=dto.session_id,
            raw_answers=dto.raw_answers,
            recommended_slugs=dto.recommended_slugs,
        )
        async with self.tm:
            await self.pref_repo.save(pref_record)

        if not dto.user_id:
            return None

        # 2. Агрегация профиля авторизованного пользователя
        user = await self.user_repo.get_by_id(dto.user_id)
        if not user:
            return None

        current_profile: dict[str, Any] = user.taste_profile or {}
        raw_answers: dict[str, Any] = dto.raw_answers or {}

        # 1. Предпочитаемые категории
        preferred_cats: list[str] = list(current_profile.get("preferred_categories", []))
        cat_ans = raw_answers.get("category")
        if isinstance(cat_ans, list):
            for c in cat_ans:
                c_str = str(c).strip()
                if c_str and c_str not in preferred_cats:
                    preferred_cats.append(c_str)
        elif isinstance(cat_ans, str) and cat_ans.strip():
            c_str = cat_ans.strip()
            if c_str not in preferred_cats:
                preferred_cats.append(c_str)

        # 2. Сладость (1.0 - 5.0)
        new_sweetness = _parse_scale_value(
            raw_answers.get("sweetness"),
            keyword_map={"сух": 1.2, "слад": 3.0, "полусух": 1.8, "полуслад": 2.6},
        )

        # 3. Тело / Плотность (1.0 - 5.0)
        new_body = _parse_scale_value(
            raw_answers.get("body"),
            keyword_map={"легк": 1.5, "плотн": 4.5, "мощн": 4.5, "средн": 3.0},
        )

        # 4. Кислотность / Свежесть (1.0 - 5.0)
        new_acid = _parse_scale_value(
            raw_answers.get("acidity"),
            keyword_map={"свежест": 4.0, "ярк": 4.5, "мягк": 2.0},
        )

        # 5. Выдержка в дубе (1.0 - 5.0)
        new_oak = _parse_scale_value(
            raw_answers.get("oak"),
            keyword_map={"дуб": 4.0, "бочк": 4.0, "без дуб": 1.5, "сталь": 1.5},
        )

        # 6. Любимые ароматы
        fav_aromas = set(current_profile.get("favorite_aromas", []))
        for aroma in _extract_aromas(raw_answers.get("aromas")):
            fav_aromas.add(aroma)

        # Расчет экспоненциального скользящего среднего (alpha = 0.35)
        updated_profile: dict[str, Any] = {
            "preferred_categories": preferred_cats,
            "sweetness_pref": _calculate_ema(current_profile.get("sweetness_pref"), new_sweetness, default=2.0),
            "body_pref": _calculate_ema(current_profile.get("body_pref"), new_body, default=3.0),
            "acidity_pref": _calculate_ema(current_profile.get("acidity_pref"), new_acid, default=3.0),
            "oak_pref": _calculate_ema(current_profile.get("oak_pref"), new_oak, default=2.5),
            "favorite_aromas": sorted(list(fav_aromas))[:15],
            "disliked_aromas": current_profile.get("disliked_aromas", []),
        }

        async with self.tm:
            await self.user_repo.update_taste_profile(dto.user_id, updated_profile)

        logger.info("Вкусовой профиль пользователя %s успешно обновлен: %s", dto.user_id, updated_profile)
        return TasteProfileDTO(**updated_profile)
