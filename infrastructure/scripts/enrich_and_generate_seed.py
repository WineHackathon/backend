#!/usr/bin/env python3
"""
Скрипт сопоставления вин каталога с фотографиями в S3, расчета Вкусовой матрицы (Taste Matrix),
генерации долгосрочных подписанных S3v2 ссылок и создания SQL-миграции с винами и гастропарами.
"""
import csv
import json
import logging
import os
import re
import uuid
import boto3
from botocore.client import Config
from datetime import datetime

from infrastructure.scripts.enrich_taste_matrix import extract_taste_matrix
from infrastructure.scripts.seed_wines import parse_grape_varieties, extract_vintage_year, determine_sugar_type

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enrich_and_seed")

# Таблица транслитерации для сопоставления русских имен файлов
TRANSLIT_MAP = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
    'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
    'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
    'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'
}

def to_latin(text: str) -> str:
    return "".join(TRANSLIT_MAP.get(c, c) for c in text.lower())

def escape_sql(val) -> str:
    if val is None:
        return "NULL"
    s = str(val).replace("'", "''")
    return f"'{s}'"

def get_food_pairings(category: str, color: str, sugar: str, body: float, acidity: float, oak: float, grapes: list[str]) -> list[dict]:
    """Генерация гастрономических сочетаний на основе органолептики вина."""
    pairings = []
    cat_lower = (category or "").lower()
    color_lower = (color or "").lower()
    sugar_lower = (sugar or "").lower()
    grapes_str = " ".join(grapes).lower()

    if "красн" in cat_lower or "красн" in color_lower:
        if body >= 3.8 or oak >= 3.0:
            pairings.append({
                "food_category": "Мясо",
                "dish_name": "Стейк рибай на углях с розмарином",
                "recommendation_reason": "Мощные танины и дубовая выдержка вина идеально расщепляют жирность мраморной говядины."
            })
            pairings.append({
                "food_category": "Сыры",
                "dish_name": "Выдержанный пармезан или твердый чеддер",
                "recommendation_reason": "Белковая структура выдержанных сыров гармонично смягчает терпкость полнотелого вина."
            })
        else:
            pairings.append({
                "food_category": "Птица",
                "dish_name": "Утиная грудка под ягодным соусом",
                "recommendation_reason": "Ягодная ароматика и элегантная кислотность подчеркивают сочность темного мяса птицы."
            })
            pairings.append({
                "food_category": "Мясо",
                "dish_name": "Телятина на гриле или нежные мясные паштеты",
                "recommendation_reason": "Деликатная танинность средней плотности не подавляет тонкий вкус телятины."
            })

    elif "бел" in cat_lower or "бел" in color_lower:
        if oak >= 3.0 or body >= 3.2:
            pairings.append({
                "food_category": "Птица",
                "dish_name": "Цыпленок или индейка в сливочно-грибном соусе",
                "recommendation_reason": "Выдержка в дубе и маслянистая текстура вина гармонично сочетаются с насыщенными сливочными блюдами из птицы."
            })
            pairings.append({
                "food_category": "Рыба",
                "dish_name": "Стейк из лосося или форели на гриле",
                "recommendation_reason": "Плотная текстура жирной рыбы требует округлого белого вина с хорошим телом и деликатным дубом."
            })
            pairings.append({
                "food_category": "Сыры",
                "dish_name": "Мягкие сыры с белой плесенью (Камамбер, Бри)",
                "recommendation_reason": "Сливочные сыры подчеркивают ванильные и ореховые тона бочковой выдержки."
            })
        elif acidity >= 4.0:
            pairings.append({
                "food_category": "Морепродукты",
                "dish_name": "Свежие черноморские устрицы и гребешки",
                "recommendation_reason": "Яркая минеральность и цитрусовая кислотность раскрывают йодистую свежесть моллюсков."
            })
            pairings.append({
                "food_category": "Рыба",
                "dish_name": "Сибас или дорадо на гриле с травами",
                "recommendation_reason": "Свежесть вина балансирует текстуру белой рыбы."
            })
        else:
            pairings.append({
                "food_category": "Птица",
                "dish_name": "Цыпленок в сливочно-чесночном соусе",
                "recommendation_reason": "Округлая текстура вина гармонирует со сливочными соусами."
            })
            pairings.append({
                "food_category": "Сыры",
                "dish_name": "Молодой козий сыр или Бри",
                "recommendation_reason": "Мягкие сыры создают шелковистый баланс с фруктовыми тонами вина."
            })

    elif "розов" in cat_lower or "розов" in color_lower:
        pairings.append({
            "food_category": "Закуски",
            "dish_name": "Брускетты с вялеными томатами и прошутто",
            "recommendation_reason": "Универсальная ягодная свежесть розе подчеркивает пикантность тапас и легких мясных деликатесов."
        })
        pairings.append({
            "food_category": "Рыба",
            "dish_name": "Тартар из лосося или креветки на гриле",
            "recommendation_reason": "Освежающий ягодный профиль идеально дополняет розовую рыбу и морепродукты."
        })

    elif "игрист" in cat_lower:
        pairings.append({
            "food_category": "Закуски",
            "dish_name": "Канапе с красной икрой или слабосоленым лососем",
            "recommendation_reason": "Тонкий перляж и высокая кислотность очищают рецепторы между закусками."
        })
        pairings.append({
            "food_category": "Морепродукты",
            "dish_name": "Мидии в белом вине",
            "recommendation_reason": "Классическое освежающее сочетание для игристых вин."
        })

    if "сладк" in sugar_lower or "полусладк" in sugar_lower:
        pairings.append({
            "food_category": "Десерты",
            "dish_name": "Тарт с грушей или ягодный чизкейк",
            "recommendation_reason": "Сладость блюда гармонирует с фруктовым сахаром вина, избегая приторности."
        })
        pairings.append({
            "food_category": "Сыры",
            "dish_name": "Сыр с голубой плесенью (Горгонзола, Дорблю)",
            "recommendation_reason": "Контраст сладкого вина и солоноватой пикантности благородной плесени."
        })

    return pairings[:3]


def main():
    s3_dir = "/tmp/strapi_extracted/prod-svoe-vino-strapi/prod-svoe-vino/strapi/uploads/"
    csv_in = "infrastructure/data/catalog.csv"
    csv_out = "infrastructure/data/catalog_enriched.csv"
    sql_out = "infrastructure/data/seed_wines.sql"

    logger.info("Сканирование распакованных файлов S3...")
    s3_files = os.listdir(s3_dir) if os.path.exists(s3_dir) else []
    logger.info(f"Найдено {len(s3_files)} файлов в локальном кэше S3.")

    # Индексирование файлов S3
    norm_index = {}
    for f in s3_files:
        if f.startswith('.'): continue
        is_thumb = f.startswith(('thumbnail_', 'small_', 'medium_', 'large_'))
        clean = re.sub(r'^(thumbnail|small|medium|large)_', '', f)
        no_hash = re.sub(r'_[a-f0-9]{10}\.', '.', clean)
        norm = no_hash.lower().replace('-', '').replace('_', '')
        if norm not in norm_index or (not is_thumb and norm_index[norm][1]):
            norm_index[norm] = (f, is_thumb)

    # Инициализация S3 клиента для генерации подписанных S3v2 ссылок
    access_key = os.getenv("S3_AWS_ACCESS_KEY_ID", "4TJ4OOLBHM05K7WSABIS")
    secret_key = os.getenv("S3_AWS_SECRET_ACCESS_KEY", "2jgO3twB3tHgPFoFXD6Lit6y1BVAXJKqrw1lT5tX")
    bucket_name = os.getenv("S3_BUCKET_NAME", "wine-hack")
    region_name = os.getenv("S3_REGION_NAME", "ru-central-1")

    s3_client = boto3.client(
        "s3",
        endpoint_url="https://firsts3.ru",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region_name,
        verify=False,
        config=Config(signature_version="s3", s3={"addressing_style": "path"})
    )

    logger.info("Чтение каталога вин...")
    with open(csv_in, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    logger.info(f"Всего строк в каталоге: {len(rows)}")

    # Уникальные вина по slug
    unique_wines = {}
    for r in rows:
        slug = (r.get("Slug") or "").strip()
        name = (r.get("Название вина") or "").strip()
        if slug and name and slug not in unique_wines:
            unique_wines[slug] = r

    total_wines = len(unique_wines)
    logger.info(f"Уникальных вин для обработки: {total_wines}")

    matched_photos = 0
    enriched_rows = []
    wine_statements = []
    pairing_statements = []

    expires_10_years = 315360000  # 10 лет

    for slug, r in unique_wines.items():
        name = (r.get("Название вина") or "").strip()
        category = (r.get("Категория") or "Тихое").strip()
        color = (r.get("Цвет") or "").strip()
        region = (r.get("Регион") or "").strip() or None
        raw_grapes = r.get("Сорт винограда") or ""
        desc = (r.get("Описание") or "").strip() or None
        winery = (r.get("Винодельня") or "").strip() or None
        raw_photo = (r.get("Название фото") or "").strip() or None

        # 1. Поиск лучшего совпадения файла в S3
        found_file = None
        if raw_photo:
            norm_p = raw_photo.lower().replace('-', '').replace('_', '')
            if norm_p in norm_index:
                found_file = norm_index[norm_p][0]

        if not found_file and slug:
            norm_s = slug.lower().replace('-', '').replace('_', '')
            if (norm_s + '.webp') in norm_index:
                found_file = norm_index[norm_s + '.webp'][0]
            elif norm_s in norm_index:
                found_file = norm_index[norm_s][0]

        if not found_file and raw_photo:
            lat_p = to_latin(raw_photo).replace('-', '').replace('_', '')
            if lat_p in norm_index:
                found_file = norm_index[lat_p][0]

        if not found_file and name:
            lat_name = to_latin(name).replace(' ', '').replace('-', '').replace('_', '')
            for norm_k, (act_f, is_t) in norm_index.items():
                if not is_t and len(norm_k) > 10 and (norm_k.replace('.webp', '') in lat_name or lat_name in norm_k):
                    found_file = act_f
                    break

        # 2. Формирование подписанной ссылки S3v2
        signed_image_url = None
        image_s3_key = None
        if found_file:
            matched_photos += 1
            image_s3_key = f"catalog/{found_file}"
            signed_image_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": image_s3_key},
                ExpiresIn=expires_10_years
            )
        elif raw_photo:
            image_s3_key = f"catalog/{raw_photo}"
            signed_image_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": image_s3_key},
                ExpiresIn=expires_10_years
            )

        # 3. Расчет Вкусовой матрицы
        sugar = determine_sugar_type(name, category, desc)
        vintage = extract_vintage_year(name)
        grapes = parse_grape_varieties(raw_grapes)
        taste = extract_taste_matrix(category=category or color, sugar_type=sugar, description=desc, name=name)

        # 4. Расчет гастропар
        pairings = get_food_pairings(
            category=category,
            color=color,
            sugar=sugar,
            body=taste["body"],
            acidity=taste["acidity"],
            oak=taste["oak"],
            grapes=grapes
        )

        wine_id = str(uuid.uuid4())
        grapes_json = json.dumps(grapes, ensure_ascii=False).replace("'", "''")
        aroma_json = json.dumps(taste["aroma_tags"], ensure_ascii=False).replace("'", "''")
        flavor_json = json.dumps(taste["flavor_tags"], ensure_ascii=False).replace("'", "''")

        # SQL Wine insert
        wine_sql = f"""INSERT INTO wines (
    id, created_at, updated_at, slug, name, category, color_desc, region,
    grape_varieties, description, winery, roskachestvo_score, sugar_type,
    vintage_year, price_rub, image_filename, image_s3_key, image_url,
    sweetness, body, acidity, oak, aroma_tags, flavor_tags, derived_attributes_confidence
) VALUES (
    '{wine_id}', NOW(), NOW(), {escape_sql(slug)}, {escape_sql(name)}, {escape_sql(category)}, {escape_sql(color or None)}, {escape_sql(region)},
    '{grapes_json}'::jsonb, {escape_sql(desc)}, {escape_sql(winery)}, 83.5, {escape_sql(sugar)},
    {vintage if vintage else 'NULL'}, NULL, {escape_sql(found_file or raw_photo)}, {escape_sql(image_s3_key)}, {escape_sql(signed_image_url)},
    {taste['sweetness']:.2f}, {taste['body']:.2f}, {taste['acidity']:.2f}, {taste['oak']:.2f},
    '{aroma_json}'::jsonb, '{flavor_json}'::jsonb, {taste['derived_attributes_confidence']:.2f}
) ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    category = EXCLUDED.category,
    color_desc = EXCLUDED.color_desc,
    region = EXCLUDED.region,
    grape_varieties = EXCLUDED.grape_varieties,
    description = EXCLUDED.description,
    winery = EXCLUDED.winery,
    sugar_type = EXCLUDED.sugar_type,
    vintage_year = EXCLUDED.vintage_year,
    image_filename = EXCLUDED.image_filename,
    image_s3_key = EXCLUDED.image_s3_key,
    image_url = EXCLUDED.image_url,
    sweetness = EXCLUDED.sweetness,
    body = EXCLUDED.body,
    acidity = EXCLUDED.acidity,
    oak = EXCLUDED.oak,
    aroma_tags = EXCLUDED.aroma_tags,
    flavor_tags = EXCLUDED.flavor_tags,
    derived_attributes_confidence = EXCLUDED.derived_attributes_confidence,
    updated_at = NOW();"""
        wine_statements.append(wine_sql)

        # SQL Pairings inserts
        for p in pairings:
            pid = str(uuid.uuid4())
            pair_sql = f"""INSERT INTO wine_food_pairings (
    id, created_at, updated_at, wine_id, food_category, dish_name, recommendation_reason
) VALUES (
    '{pid}', NOW(), NOW(), (SELECT id FROM wines WHERE slug = {escape_sql(slug)}),
    {escape_sql(p['food_category'])}, {escape_sql(p['dish_name'])}, {escape_sql(p['recommendation_reason'])}
);"""
            pairing_statements.append(pair_sql)

        enriched_rows.append({
            "Slug": slug,
            "Название вина": name,
            "Категория": category,
            "Цвет": color,
            "Регион": region,
            "Сорт винограда": ", ".join(grapes),
            "Описание": desc,
            "Винодельня": winery,
            "Название фото": found_file or raw_photo,
            "S3_Key": image_s3_key,
            "Signed_Image_URL": signed_image_url,
            "Sweetness": taste["sweetness"],
            "Body": taste["body"],
            "Acidity": taste["acidity"],
            "Oak": taste["oak"],
            "Aroma_Tags": ", ".join(taste["aroma_tags"]),
            "Flavor_Tags": ", ".join(taste["flavor_tags"]),
            "Pairings": "; ".join(f"{p['food_category']}: {p['dish_name']}" for p in pairings),
        })

    logger.info(f"Сопоставлено фотографий: {matched_photos}/{total_wines} ({matched_photos/total_wines*100:.1f}%)")

    # 5. Запись обогащенного CSV
    fieldnames = list(enriched_rows[0].keys())
    with open(csv_out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)
    logger.info(f"Обогащенный CSV сохранен: {csv_out}")

    # 6. Формирование финального SQL файла
    sql_header = [
        "-- ============================================================================",
        "-- SQL Seed Migration: Каталог вин, Вкусовая матрица, Подписанные S3 URL и Гастропары",
        f"-- Сгенерировано: {datetime.utcnow().isoformat()} UTC",
        "-- ============================================================================",
        "",
        "CREATE TABLE IF NOT EXISTS wines (",
        "    id UUID NOT NULL PRIMARY KEY,",
        "    slug VARCHAR(255) NOT NULL UNIQUE,",
        "    name VARCHAR(500) NOT NULL,",
        "    category VARCHAR(100) NOT NULL,",
        "    color_desc VARCHAR(255),",
        "    region VARCHAR(255),",
        "    grape_varieties JSONB NOT NULL DEFAULT '[]'::jsonb,",
        "    description TEXT,",
        "    winery VARCHAR(255),",
        "    roskachestvo_score FLOAT,",
        "    sugar_type VARCHAR(50),",
        "    vintage_year INTEGER,",
        "    price_rub FLOAT,",
        "    image_filename VARCHAR(500),",
        "    image_s3_key VARCHAR(500),",
        "    image_url TEXT,",
        "    sweetness FLOAT,",
        "    body FLOAT,",
        "    acidity FLOAT,",
        "    oak FLOAT,",
        "    aroma_tags JSONB NOT NULL DEFAULT '[]'::jsonb,",
        "    flavor_tags JSONB NOT NULL DEFAULT '[]'::jsonb,",
        "    derived_attributes_confidence FLOAT,",
        "    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,",
        "    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS wine_food_pairings (",
        "    id UUID NOT NULL PRIMARY KEY,",
        "    wine_id UUID NOT NULL REFERENCES wines(id) ON DELETE CASCADE,",
        "    food_category VARCHAR(100) NOT NULL,",
        "    dish_name VARCHAR(255) NOT NULL,",
        "    recommendation_reason TEXT,",
        "    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,",
        "    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL",
        ");",
        "",
        "CREATE INDEX IF NOT EXISTS ix_wines_name ON wines (name);",
        "CREATE INDEX IF NOT EXISTS ix_wines_winery ON wines (winery);",
        "CREATE INDEX IF NOT EXISTS ix_wines_category ON wines (category);",
        "CREATE INDEX IF NOT EXISTS ix_pairings_wine_id ON wine_food_pairings (wine_id);",
        "",
        "BEGIN;",
        ""
    ]

    all_sql = sql_header + wine_statements + [""] + pairing_statements + [
        "",
        "COMMIT;",
        f"-- Всего вин: {len(wine_statements)}, Всего гастропар: {len(pairing_statements)}",
        f"-- Успешно сопоставлено фото: {matched_photos}/{total_wines} ({matched_photos/total_wines*100:.1f}%)"
    ]

    with open(sql_out, "w", encoding="utf-8") as f:
        f.write("\n".join(all_sql))

    logger.info(f"Финальный SQL дамп сохранен: {sql_out} ({len(wine_statements)} вин, {len(pairing_statements)} гастропар)")


if __name__ == "__main__":
    main()
