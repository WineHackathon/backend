"""
Двухуровневый сервис извлечения намерений (Intent & Entity Extractor) для AI-Сомелье:
1. Нейросетевой парсер (LLM с Pydantic JSON-схемой).
2. Высокоскоростной детерминированный fallback на регулярных выражениях и винном словаре.
"""
import json
import logging
import re
from typing import Any
from application.dto.wine_intent import WineSearchIntent

logger = logging.getLogger(__name__)

# Винный словарь для эвристического парсера
GRAPE_VARIETIES = [
    "каберне совиньон", "каберне фран", "каберне", "саперави", "пино нуар", "мерло",
    "шираз", "сира", "красностоп золотовский", "красностоп", "цимлянский черный",
    "рислинг", "шардоне", "совиньон блан", "совиньон", "алиготе", "ркацители",
    "мускат", "кокур", "виорика", "автохтон",
]

FOOD_PAIRING_MAP = {
    "мясо / стейк": ["стейк", "рибай", "филе миньон", "говядин", "мяс", "баранин", "шашлык", "бургер", "дичь"],
    "рыба / морепродукты": ["рыб", "морепродукт", "креветк", "миди", "устриц", "лосос", "форел", "тунец", "сибас", "дорад"],
    "сыры": ["сыр", "пармезан", "дорблю", "камамбер", "бри", "чеддер"],
    "птица": ["птиц", "куриц", "утк", "индейк"],
    "паста / пицца": ["паст", "пицц", "ризотто"],
    "десерты": ["десерт", "шоколад", "торт", "фрукт", "ягод", "пирож"],
}


class IntentExtractor:
    """Сервис извлечения сущностей и фильтров из текстового запроса пользователя."""

    @staticmethod
    def extract_heuristic(text: str) -> WineSearchIntent:
        """
        Высокоскоростной детерминированный экстрактор (Anti-Govnokod):
        Мгновенно извлекает категорию, гастропару, тело, сахар и бюджет без внешних вызовов.
        """
        t = text.lower()

        # 1. Категория вина (явное упоминание пользователем)
        explicit_category = None
        if any(k in t for k in ("игрист", "шампан", "просекко", "prosecco", "кава", "cava", "брют", "brut", "спуманте", "spumante", "петнат", "petnat", "frizzante", "фриззанте")):
            explicit_category = "Игристое"
        elif "красн" in t:
            explicit_category = "Красное"
        elif "розов" in t:
            explicit_category = "Розовое"
        elif "оранж" in t:
            explicit_category = "Оранжевое"
        elif "бел" in t:
            explicit_category = "Белое"

        category = explicit_category

        # 2. Тип сахара
        sugar_type = None
        if "экстра брют" in t or "extra brut" in t:
            sugar_type = "Экстра брют"
        elif "брют" in t or "brut" in t:
            sugar_type = "Брют"
        elif "полусух" in t:
            sugar_type = "Полусухое"
        elif "сух" in t:
            sugar_type = "Сухое"
        elif "полусладк" in t:
            sugar_type = "Полусладкое"
        elif "сладк" in t:
            sugar_type = "Сладкое"

        # 3. Гастропара
        food_pairing = None
        for pair_name, keywords in FOOD_PAIRING_MAP.items():
            if any(kw in t for kw in keywords):
                food_pairing = pair_name
                break

        # Если пара стейк/мясо и категория не указана явно — стейк рибай требует красного вина
        if food_pairing == "мясо / стейк" and not category:
            category = "Красное"
        elif food_pairing == "рыба / морепродукты" and not category:
            category = "Белое"

        # 4. Сорт винограда
        grape = None
        for g in GRAPE_VARIETIES:
            if g in t:
                grape = g
                break

        # 5. Плотность/тело вина (body)
        target_body = None
        if any(w in t for w in ("полнотел", "плотн", "мощн", "насыщенн", "танинн", "терпк")):
            target_body = 4.5
        elif any(w in t for w in ("легк", "воздушн", "тонк")):
            target_body = 2.0

        # 6. Бюджет (максимальная цена)
        max_price = None
        price_match = re.search(r"(?:до|бюджет|около|не дороже|цена до)\s*(\d+[\s\d]*)\s*(?:руб|р|\b)", t)
        if price_match:
            try:
                num_str = price_match.group(1).replace(" ", "")
                val = float(num_str)
                if 200 <= val <= 1_000_000:
                    max_price = val
            except ValueError:
                pass

        # 7. Регион
        region = None
        if any(r in t for r in ("крым", "севастопол")):
            region = "Крым"
        elif any(r in t for r in ("кубан", "краснодар")):
            region = "Кубань"
        elif any(r in t for r in ("дон", "долин")):
            region = "Долина Дона"
        elif "дагестан" in t:
            region = "Дагестан"

        # Ключевые слова
        keywords = []
        if grape:
            keywords.append(grape)
        if food_pairing:
            keywords.append(food_pairing.split("/")[0].strip())

        return WineSearchIntent(
            category=category,
            explicit_category=explicit_category,
            sugar_type=sugar_type,
            food_pairing=food_pairing,
            grape_variety=grape,
            region=region,
            target_body=target_body,
            max_price_rub=max_price,
            search_keywords=keywords,
            is_recommendation_request=True,
        )

    async def extract_intent(self, text: str, llm_client: Any | None = None) -> WineSearchIntent:
        """
        Двухуровневое извлечение:
        Если доступен LLM-клиент с API-ключом — выполняется структурированное извлечение через модель.
        При ошибке или недоступности сети — мгновенный переход на эвристический парсер.
        """
        # Сначала получаем сверхбыстрый детерминированный результат (<0.5 мс)
        base_intent = self.extract_heuristic(text)

        # Если эвристика уверенно определила категорию, гастропару или сорт — не делаем лишний сетевой запрос к LLM!
        if base_intent.category or base_intent.food_pairing or base_intent.grape_variety:
            return base_intent

        if not llm_client or not getattr(llm_client, "api_key", None):
            return base_intent

        system_prompt = (
            "You are an expert sommelier entity extraction engine.\n"
            "Analyze the user query and extract wine search intent into a STRICT JSON object with these fields:\n"
            "- category: string or null ('Красное', 'Белое', 'Розовое', 'Игристое')\n"
            "- sugar_type: string or null ('Сухое', 'Полусухое', 'Полусладкое', 'Сладкое')\n"
            "- food_pairing: string or null (e.g. 'мясо / стейк', 'рыба / морепродукты', 'сыры', etc.)\n"
            "- grape_variety: string or null\n"
            "- region: string or null ('Кубань', 'Крым', 'Долина Дона', 'Дагестан')\n"
            "- target_body: float (1.0 to 5.0) or null (e.g. 4.5 for full-bodied/полнотелое)\n"
            "- max_price_rub: float or null\n"
            "- search_keywords: array of strings\n"
            "Output ONLY raw JSON. No markdown, no prose."
        )

        try:
            raw_response = await llm_client.generate_response(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": text}],
            )
            # Очистка возможного markdown
            clean_json = raw_response.strip()
            if clean_json.startswith("```"):
                lines = clean_json.split("\n")
                clean_json = "\n".join(lines[1:-1])

            data = json.loads(clean_json)
            # Слияние: если LLM не распознала очевидную категорию или гастропару, берем из эвристики
            return WineSearchIntent(
                category=data.get("category") or base_intent.category,
                sugar_type=data.get("sugar_type") or base_intent.sugar_type,
                food_pairing=data.get("food_pairing") or base_intent.food_pairing,
                grape_variety=data.get("grape_variety") or base_intent.grape_variety,
                region=data.get("region") or base_intent.region,
                target_body=data.get("target_body") or base_intent.target_body,
                max_price_rub=data.get("max_price_rub") or base_intent.max_price_rub,
                search_keywords=data.get("search_keywords") or base_intent.search_keywords,
                is_recommendation_request=True,
            )
        except Exception as exc:
            logger.warning(f"Ошибка LLM intent extraction ({exc}), используем эвристический результат")
            return base_intent


intent_extractor = IntentExtractor()
