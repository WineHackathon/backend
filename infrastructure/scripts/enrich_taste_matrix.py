"""
Скрипт и модуль интеллектуального извлечения органолептических признаков
Вкусовой матрицы (Taste Matrix) из описаний вин датасета «Своё Вино».
"""
import re
from typing import TypedDict


class TasteMatrixResult(TypedDict):
    sweetness: float
    body: float
    acidity: float
    oak: float
    aroma_tags: list[str]
    flavor_tags: list[str]
    derived_attributes_confidence: float


# Словарь лексических маркеров ароматов и вкусов российских вин
AROMA_LEXICON = [
    # Ягоды
    ("черная смородина", ["черная смородина", "черной смородины", "черносмородинов"]),
    ("вишня", ["вишня", "вишни", "вишнев"]),
    ("черешня", ["черешня", "черешни"]),
    ("ежевика", ["ежевика", "ежевики", "ежевичн"]),
    ("малина", ["малина", "малины", "малинов"]),
    ("клубника", ["клубника", "клубники", "клубничн"]),
    ("земляника", ["земляника", "земляники"]),
    ("брусника", ["брусника", "брусники"]),
    ("слива", ["слива", "сливы", "сливов"]),
    ("чернослив", ["чернослив", "чернослива"]),
    # Фрукты
    ("зеленое яблоко", ["зеленое яблоко", "зеленого яблока"]),
    ("яблоко", ["яблоко", "яблока", "яблочн"]),
    ("груша", ["груша", "груши", "грушев"]),
    ("персик", ["персик", "персика", "персиков"]),
    ("абрикос", ["абрикос", "абрикоса", "абрикосов", "курага", "кураги"]),
    ("айва", ["айва", "айвы"]),
    ("инжир", ["инжир", "инжира"]),
    ("цукаты", ["цукаты", "цукатов"]),
    ("мед", ["мед", "меда", "медов"]),
    # Цитрусовые
    ("лайм", ["лайм", "лайма"]),
    ("лимон", ["лимон", "лимона", "лимонн"]),
    ("грейпфрут", ["грейпфрут", "грейпфрута"]),
    ("апельсин", ["апельсин", "апельсина"]),
    # Цветочные и травянистые
    ("белые цветы", ["белые цветы", "белых цветов", "белоцветочный"]),
    ("роза", ["роза", "розы", "лепестки роз"]),
    ("фиалка", ["фиалка", "фиалки"]),
    ("акация", ["акация", "акации"]),
    ("полевые травы", ["травы", "полевые травы", "степные травы"]),
    # Дуб, пряности и выдержка
    ("дуб", ["дуб", "дуба", "дубов", "баррик", "бочк"]),
    ("ваниль", ["ваниль", "ванили", "ванильн"]),
    ("шоколад", ["шоколад", "шоколада", "шоколадн"]),
    ("кофе", ["кофе", "кофейн"]),
    ("табак", ["табак", "табака", "табачн"]),
    ("перец", ["перец", "перца", "перечн"]),
    ("гвоздика", ["гвоздика", "гвоздики"]),
    ("корица", ["корица", "корицы"]),
    ("кожа", ["кожа", "кожи", "кожан"]),
    # Минеральные ноты
    ("минералы", ["минерал", "минеральн", "мокрый камень", "кремень", "морской"]),
]


def extract_taste_matrix(
    category: str | None = None,
    sugar_type: str | None = None,
    description: str | None = None,
) -> TasteMatrixResult:
    """
    Эвристический анализ описания вина для формирования вкусовой матрицы:
    - sweetness: 1.0 (экстра-сухое) ... 5.0 (десертное)
    - body: 1.0 (лёгкое) ... 5.0 (мощное/полнотелое)
    - acidity: 1.0 (мягкая) ... 5.0 (яркая/хрустящая)
    - oak: 1.0 (без дуба) ... 5.0 (тяжелый дуб)
    - aroma_tags / flavor_tags: теги нот
    - derived_attributes_confidence: оценка уверенности от 0.0 до 1.0
    """
    desc = (description or "").lower()
    cat = (category or "Тихое").lower()
    sugar = (sugar_type or "Сухое").lower()

    # 1. Сладость (Sweetness)
    if "экстра брют" in desc or "брют натюр" in desc:
        sweetness = 1.0
    elif "брют" in sugar or "сухое" in sugar or "сух" in desc:
        sweetness = 1.2
    elif "полусухое" in sugar or "полусух" in desc:
        sweetness = 2.5
    elif "полусладкое" in sugar or "полусладк" in desc:
        sweetness = 3.5
    elif "сладкое" in sugar or "десертное" in sugar or "сладк" in desc:
        sweetness = 4.5
    else:
        sweetness = 2.0

    # 2. Плотность / Тело (Body)
    if "красн" in cat:
        body = 4.0
        if any(w in desc for w in ["полнотелое", "мощное", "плотное", "танинное", "насыщенное"]):
            body = 4.6
        elif any(w in desc for w in ["легкое", "элегантное", "деликатное", "питкое"]):
            body = 2.8
    elif "бел" in cat:
        body = 2.2
        if any(w in desc for w in ["плотное", "маслянистое", "округлое", "сливочное", "выдержанное"]):
            body = 3.6
        elif any(w in desc for w in ["легкое", "хрупкое", "тонкое"]):
            body = 1.6
    elif "розов" in cat:
        body = 2.4
    elif "игрист" in cat:
        body = 2.0
    else:
        body = 3.0

    # 3. Кислотность / Свежесть (Acidity)
    if "бел" in cat or "игрист" in cat:
        acidity = 3.8
        if any(w in desc for w in ["хрустящая", "звонкая", "высокая", "яркая", "освежающее", "минеральн"]):
            acidity = 4.5
        elif any(w in desc for w in ["мягкая", "умеренная", "сглаженная"]):
            acidity = 2.8
    elif "красн" in cat:
        acidity = 3.0
        if any(w in desc for w in ["свежее", "сочное", "яркая кислотность"]):
            acidity = 3.6
        elif any(w in desc for w in ["мягкое", "бархатистое", "зрелое"]):
            acidity = 2.4
    else:
        acidity = 3.2

    # 4. Выдержка в дубе (Oak)
    oak_markers = ["дуб", "баррик", "бочк", "выдержк", "ваниль", "тост", "дым"]
    no_oak_markers = ["сталь", "стальных", "без выдержки в дубе", "нейтральн"]

    if any(w in desc for w in no_oak_markers):
        oak = 1.1
    elif any(w in desc for w in oak_markers):
        oak = 4.2
    elif "красн" in cat:
        oak = 2.5
    else:
        oak = 1.3

    # 5. Извлечение тегов аромата и вкуса
    detected_aromas: list[str] = []
    detected_flavors: list[str] = []

    for tag, stems in AROMA_LEXICON:
        for stem in stems:
            if re.search(r"\b" + re.escape(stem), desc):
                if tag not in detected_aromas:
                    detected_aromas.append(tag)
                break

    # Разделение между ароматом и вкусом (ноты дерева/шоколада/сливы часто во вкусе)
    flavor_candidates = {"шоколад", "слива", "табак", "кофе", "минералы", "перец", "ваниль"}
    for tag in detected_aromas:
        if tag in flavor_candidates and tag not in detected_flavors:
            detected_flavors.append(tag)

    # Оценка уверенности
    if len(detected_aromas) >= 3:
        confidence = 0.95
    elif len(detected_aromas) >= 1:
        confidence = 0.85
    else:
        confidence = 0.60

    return {
        "sweetness": round(sweetness, 2),
        "body": round(body, 2),
        "acidity": round(acidity, 2),
        "oak": round(oak, 2),
        "aroma_tags": detected_aromas[:10],
        "flavor_tags": detected_flavors[:10],
        "derived_attributes_confidence": confidence,
    }
