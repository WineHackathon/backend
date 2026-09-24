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
    ("черная смородина", [r"черн\w*\s+смородин\w*", r"черносмородин\w*"]),
    ("красная смородина", [r"красн\w*\s+смородин\w*"]),
    ("вишня", [r"вишн\w*"]),
    ("черешня", [r"черешн\w*"]),
    ("ежевика", [r"ежевик\w*", r"ежевичн\w*"]),
    ("малина", [r"малин\w*"]),
    ("клубника", [r"клубник\w*", r"клубничн\w*"]),
    ("земляника", [r"земляник\w*"]),
    ("брусника", [r"брусник\w*"]),
    ("черника", [r"черник\w*"]),
    ("слива", [r"слив\w*"]),
    ("чернослив", [r"чернослив\w*"]),
    ("лесные ягоды", [r"лесн\w*\s+ягод\w*", r"красн\w*\s+ягод\w*", r"черн\w*\s+ягод\w*", r"темн\w*\s+ягод\w*"]),
    # Фрукты
    ("зеленое яблоко", [r"зелен\w*\s+яблок\w*"]),
    ("яблоко", [r"яблок\w*"]),
    ("груша", [r"груш\w*"]),
    ("персик", [r"персик\w*"]),
    ("абрикос", [r"абрикос\w*", r"кураг\w*"]),
    ("айва", [r"айв\w*"]),
    ("инжир", [r"инжир\w*"]),
    ("белые фрукты", [r"бел\w*\s+фрукт\w*"]),
    ("тропические фрукты", [r"тропическ\w*", r"манго", r"маракуй\w*", r"ананас\w*", r"банан\w*"]),
    ("сухофрукты", [r"сухофрукт\w*", r"изюм\w*"]),
    ("мед", [r"мед\b", r"медов\w*", r"меда\b"]),
    # Цитрусовые
    ("цитрусовые", [r"цитрус\w*"]),
    ("лайм", [r"лайм\w*"]),
    ("лимон", [r"лимон\w*"]),
    ("грейпфрут", [r"грейпфрут\w*"]),
    ("апельсин", [r"апельсин\w*"]),
    # Цветочные и травянистые
    ("белые цветы", [r"бел\w*\s+цвет\w*", r"белоцветочн\w*"]),
    ("полевые цветы", [r"весенн\w*\s+цвет\w*", r"полев\w*\s+цвет\w*", r"цветочн\w*"]),
    ("роза", [r"роз\w*"]),
    ("фиалка", [r"фиалк\w*"]),
    ("акация", [r"акаци\w*"]),
    ("травы", [r"трав\w*"]),
    # Выдержка, пряности, третичные ароматы
    ("дуб", [r"дуб\w*", r"баррик\w*", r"бочк\w*", r"barrel", r"cask"]),
    ("ваниль", [r"ванил\w*"]),
    ("шоколад", [r"шоколад\w*"]),
    ("кофе", [r"кофе\w*"]),
    ("табак", [r"табак\w*"]),
    ("пряности", [r"прян\w*", r"специ\w*", r"гвоздик\w*", r"кориц\w*", r"мускат\w*"]),
    ("перец", [r"перец", r"перц\w*"]),
    ("кожа", [r"кож\w*"]),
    ("бриошь и выпечка", [r"бриош\w*", r"тост\w*", r"хлеб\w*", r"выпечк\w*"]),
    ("сливочные ноты", [r"сливочн\w*", r"масл\w*", r"крем\w*"]),
    ("минералы", [r"минерал\w*", r"кремен\w*", r"мокрый камень", r"морск\w*"]),
]

FLAVOR_LEXICON = [
    ("спелые ягоды", [r"ягодн\w*", r"лесные ягоды"]),
    ("фруктовое", [r"фруктов\w*"]),
    ("цитрусы", [r"цитрус\w*", r"лайм\w*", r"лимон\w*", r"грейпфрут\w*"]),
    ("минеральность", [r"минеральн\w*", r"минерал\w*"]),
    ("сливочные ноты", [r"сливочн\w*", r"маслянист\w*"]),
    ("пряности", [r"прян\w*", r"специ\w*", r"перечн\w*"]),
    ("шоколад", [r"шоколад\w*"]),
    ("ваниль", [r"ванил\w*"]),
    ("дуб и древесные тона", [r"древесн\w*", r"дубов\w*", r"бочк\w*", r"баррик\w*"]),
    ("сухофрукты", [r"сухофрукт\w*", r"изюм\w*", r"чернослив\w*"]),
    ("мед", [r"медов\w*", r"мед\b"]),
    ("кофе и табак", [r"кофейн\w*", r"кофе\b", r"табачн\w*", r"табак\b"]),
    ("орехи", [r"орех\w*", r"миндал\w*"]),
    ("вишня и черешня", [r"вишн\w*", r"черешн\w*"]),
    ("черная смородина", [r"смородин\w*"]),
    ("зеленое яблоко", [r"зелен\w*\s+яблок\w*"]),
]


def extract_taste_matrix(
    category: str | None = None,
    sugar_type: str | None = None,
    description: str | None = None,
    name: str | None = None,
) -> TasteMatrixResult:
    """
    Эвристический анализ названия и описания вина для формирования вкусовой матрицы:
    - sweetness: 1.0 (экстра-сухое) ... 5.0 (десертное)
    - body: 1.0 (лёгкое) ... 5.0 (мощное/полнотелое)
    - acidity: 1.0 (мягкая) ... 5.0 (яркая/хрустящая)
    - oak: 1.0 (без дуба) ... 5.0 (тяжелый дуб)
    - aroma_tags / flavor_tags: теги нот
    - derived_attributes_confidence: оценка уверенности от 0.0 до 1.0
    """
    full_text = f"{name or ''} {description or ''}".lower().replace("ё", "е")
    desc = full_text
    cat = (category or "Тихое").lower()
    sugar = (sugar_type or "Сухое").lower()

    # 1. Сладость (Sweetness)
    if any(w in desc for w in ["экстра брют", "extra brut", "брют натюр", "brut nature", "zero dosage"]):
        sweetness = 1.0
    elif any(w in sugar for w in ["брют", "brut", "сухое", "сухой", "dry"]) or "сух" in desc:
        sweetness = 1.2
    elif any(w in sugar for w in ["полусухое", "полусухой", "semi-dry"]) or "полусух" in desc:
        sweetness = 2.4
    elif any(w in sugar for w in ["полусладкое", "полусладкий", "semi-sweet"]) or "полусладк" in desc:
        sweetness = 3.6
    elif any(w in sugar for w in ["сладкое", "сладкий", "sweet", "десертное", "ликёрное", "ликерное"]) or any(w in desc for w in ["сладк", "десертн"]):
        sweetness = 4.6
    else:
        sweetness = 1.5

    # 2. Плотность / Тело (Body)
    if "красн" in cat:
        body = 3.8
        if any(w in desc for w in ["легк", "хрупк", "тонк", "питк", "деликатн"]):
            body = 2.6
        elif any(w in desc for w in ["полнотел", "мощн", "плотн", "танинн", "насыщенн", "густ"]):
            body = 4.5
        elif any(w in desc for w in ["среднетел", "сбалансированн"]):
            body = 3.5
    elif "бел" in cat:
        body = 2.2
        if any(w in desc for w in ["легк", "хрупк", "тонк"]):
            body = 1.6
        elif any(w in desc for w in ["полнотел", "плотн", "маслянист", "округл", "сливочн", "объемн"]):
            body = 3.6
        elif any(w in desc for w in ["среднетел"]):
            body = 3.0
    elif "розов" in cat:
        body = 2.4
    elif "игрист" in cat:
        body = 2.0
    else:
        body = 3.0

    # 3. Кислотность / Свежесть (Acidity)
    if "бел" in cat or "игрист" in cat:
        acidity = 3.8
        if any(w in desc for w in ["хрустящ", "звонк", "высок", "ярк", "освежающ", "минеральн", "лайм", "грейпфрут", "свеж"]):
            acidity = 4.4
        elif any(w in desc for w in ["мягк", "умеренн", "сглаженн"]):
            acidity = 2.8
    elif "красн" in cat:
        acidity = 3.0
        if any(w in desc for w in ["свеж", "сочн", "ярк"]):
            acidity = 3.6
        elif any(w in desc for w in ["мягк", "бархатист", "зрел", "шелковист"]):
            acidity = 2.5
    else:
        acidity = 3.2

    # 4. Выдержка в дубе (Oak)
    oak_markers = ["дуб", "баррик", "бочк", "выдерж", "ванил", "тост", "дым", "табак", "кориц", "шоколад", "barrel", "barrique", "cask", "oaked"]
    no_oak_markers = ["сталь", "стальн", "без выдержки в дубе", "нейтральн", "нержавеющ", "unoaked", "stainless"]

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

    for tag, patterns in AROMA_LEXICON:
        for pat in patterns:
            if re.search(pat, desc):
                if tag not in detected_aromas:
                    detected_aromas.append(tag)
                break

    for tag, patterns in FLAVOR_LEXICON:
        for pat in patterns:
            if re.search(pat, desc):
                if tag not in detected_flavors:
                    detected_flavors.append(tag)
                break

    # Оценка уверенности
    if len(detected_aromas) >= 3 or len(detected_flavors) >= 3:
        confidence = 0.95
    elif len(detected_aromas) >= 1 or len(detected_flavors) >= 1:
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
