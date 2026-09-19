"""
Движок подбора вин на основе Вкусовой матрицы (Recommendation Engine).
Расчет расстояния в 4D-пространстве вкуса (sweetness, body, acidity, oak)
в сочетании с коэффициентом Жаккара по ароматическим и вкусовым тегам.
"""
import math
from typing import Any


class SommelierRecommendationEngine:
    """Алгоритм сопоставления вин с профилем предпочтений пользователя."""

    def rank_candidates(
        self,
        candidates: list[dict[str, Any]],
        target_sweetness: float = 1.2,
        target_body: float = 3.0,
        target_acidity: float = 3.0,
        target_oak: float = 2.0,
        target_aromas: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Ранжирование списка вин по близости к желаемому профилю.
        Возвращает отсортированный список вин (наиболее релевантные первые).
        """
        target_aroma_set = {a.lower().strip() for a in (target_aromas or [])}

        def compute_score(wine: dict[str, Any]) -> float:
            # 1. Расчет евклидова расстояния по 4 измерениям вкуса
            w_s = wine.get("sweetness") or 2.0
            w_b = wine.get("body") or 3.0
            w_a = wine.get("acidity") or 3.0
            w_o = wine.get("oak") or 2.0

            dist_sq = (
                1.5 * ((w_s - target_sweetness) ** 2) +
                1.0 * ((w_b - target_body) ** 2) +
                1.0 * ((w_a - target_acidity) ** 2) +
                1.0 * ((w_o - target_oak) ** 2)
            )
            taste_distance = math.sqrt(dist_sq)

            # 2. Расчет сходства ароматических дескрипторов (коэффициент Жаккара)
            wine_aromas = {a.lower().strip() for a in wine.get("aroma_tags", [])}
            wine_flavors = {f.lower().strip() for f in wine.get("flavor_tags", [])}
            all_wine_tags = wine_aromas | wine_flavors

            aroma_similarity = 0.0
            if target_aroma_set and all_wine_tags:
                intersection = target_aroma_set & all_wine_tags
                union = target_aroma_set | all_wine_tags
                aroma_similarity = len(intersection) / len(union)

            # Итоговый скор: меньшее расстояние вкуса и большее сходство ароматов дают меньший скор
            total_score = taste_distance - (1.5 * aroma_similarity)
            return total_score

        return sorted(candidates, key=compute_score)
