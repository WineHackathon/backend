"""
Прикладной сервис фоновой агрегации вкусового профиля пользователя (Taste Profile).
Сохраняет сырые данные диалога и обновляет экспоненциальное скользящее среднее (EMA) вкусов.
"""
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.models.preference_history import UserPreferenceHistory
from application.adapters.database.repositories.user_repo import UserRepository
from application.adapters.database.repositories.preference_repo import PreferenceRepository
from application.adapters.database.transaction_manager import TransactionManager

logger = logging.getLogger(__name__)


class TasteProfileService:
    """Сервис обновления и агрегации вкусового профиля пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.pref_repo = PreferenceRepository(session)
        self.tm = TransactionManager(session)

    async def record_preferences_and_update_profile(
        self,
        user_id: uuid.UUID | None,
        session_id: str,
        raw_answers: dict[str, str],
        recommended_slugs: list[str],
    ) -> dict:
        """
        Фоновая задача (на фоне на бэке):
        1. Сохранение истории предпочтений (сырые данные) в UserPreferenceHistory.
        2. Агрегация вкусового профиля пользователя (User.taste_profile) через EMA.
        """
        # 1. Сохранение сырой истории
        pref_record = UserPreferenceHistory(
            user_id=user_id,
            session_id=session_id,
            raw_answers=raw_answers,
            recommended_slugs=recommended_slugs,
        )
        async with self.tm:
            await self.pref_repo.save(pref_record)

        if not user_id:
            return {}

        # 2. Агрегация профиля авторизованного пользователя
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            return {}

        current_profile = user.taste_profile or {}

        # Маппинг ответов на числовые шкалы
        # 1. Категория
        cat = raw_answers.get("category", "")
        preferred_cats = current_profile.get("preferred_categories", [])
        if cat and cat not in preferred_cats:
            preferred_cats.append(cat)

        # 2. Сладость (1.0 - 5.0)
        sweet_ans = raw_answers.get("sweetness", "").lower()
        new_sweetness = 1.2 if "сух" in sweet_ans else (3.0 if "слад" in sweet_ans else None)

        # 3. Тело / Плотность (1.0 - 5.0)
        body_ans = raw_answers.get("body", "").lower()
        new_body = 1.5 if "легк" in body_ans else (4.5 if "плотн" in body_ans else 3.0)

        # 4. Кислотность / Свежесть (1.0 - 5.0)
        acid_ans = raw_answers.get("acidity", "").lower()
        new_acid = 4.0 if "свежест" in acid_ans else 2.0

        # 5. Выдержка в дубе (1.0 - 5.0)
        oak_ans = raw_answers.get("oak", "").lower()
        new_oak = 4.0 if "дуб" in oak_ans or "бочк" in oak_ans else 2.0

        # 6. Ароматы
        aroma_ans = raw_answers.get("aromas", "")
        fav_aromas = set(current_profile.get("favorite_aromas", []))
        if aroma_ans:
            for item in aroma_ans.replace(";", ",").split(","):
                cleaned = item.strip().lower()
                if cleaned:
                    fav_aromas.add(cleaned)

        # Расчет экспоненциального скользящего среднего (alpha = 0.35)
        alpha = 0.35

        def ema(curr: float | None, new_val: float | None, default: float) -> float:
            if new_val is None:
                return curr if curr is not None else default
            if curr is None:
                return new_val
            return round(curr * (1 - alpha) + new_val * alpha, 2)

        updated_profile = {
            "preferred_categories": preferred_cats,
            "sweetness_pref": ema(current_profile.get("sweetness_pref"), new_sweetness, 2.0),
            "body_pref": ema(current_profile.get("body_pref"), new_body, 3.0),
            "acidity_pref": ema(current_profile.get("acidity_pref"), new_acid, 3.0),
            "oak_pref": ema(current_profile.get("oak_pref"), new_oak, 2.5),
            "favorite_aromas": list(fav_aromas)[:15],
            "disliked_aromas": current_profile.get("disliked_aromas", []),
        }

        async with self.tm:
            await self.user_repo.update_taste_profile(user_id, updated_profile)

        logger.info(f"Вкусовой профиль пользователя {user_id} успешно обновлен: {updated_profile}")
        return updated_profile
