# 06. Текущий статус и дальнейшие шаги (Roadmap)

## 1. Текущее состояние проекта (Status: Ready for Deployment)

✅ **Все 10 репозиториев созданы и запушены в [WineHackathon](https://github.com/WineHackathon)**:
- `infra` — Docker Compose стенд и Nginx Gateway;
- `database` — модели SQLAlchemy 2.0 async и сессии;
- `protos` — схемы Pydantic v2;
- `recognition-service` — сканер `/v1/eval/predict`, S3 аплоад, Redis Streams RPC;
- `catalog-service` — каталог вин, фильтрация, Sync API;
- `auth-service` — Email/пароль + Яндекс ID OAuth 2.0;
- `user-service` — винный погреб и история сканирований;
- `sommelier-service` — AI-сомелье с RAG и гастропарами;
- `ml-service` — воркер на GPU, PyTorch эмбеддинги, векторный поиск;
- `frontend` — веб-интерфейс со сканером и чатом;
- `backend` — мастер-спецификация платформы.

---

## 2. Пошаговые дальнейшие шаги

### Шаг 1: Запуск инфраструктурного стенда
В директории `infra/`:
```bash
cd infra/
cp .env.example .env
docker compose up -d --build
```
Проверить статус контейнеров:
```bash
docker compose ps
curl http://localhost:8080/health
```

### Шаг 2: Сидинг каталога вин
Запуск парсера датасета `strapi_output0709.csv` для загрузки 6 325 вин в PostgreSQL:
```bash
python catalog-service/scripts/seed_wines.py \
  --csv-path "Датасет/strapi_output0709.csv" \
  --uploads-dir "Датасет/prod-svoe-vino-strapi/prod-svoe-vino/strapi/uploads"
```

### Шаг 3: Построение векторного индекса для ML-воркера
Прогон эталонных изображений и генерация векторного индекса `wine_embeddings_index.npz`:
```bash
python ml-service/scripts/build_index.py \
  --csv-path "Датасет/strapi_output0709.csv" \
  --images-dir "Датасет/prod-svoe-vino-strapi/prod-svoe-vino/strapi/uploads" \
  --output "ml-service/data/wine_embeddings_index.npz"
```

### Шаг 4: Прогон бенчмарка хакатона
Запуск чекера `participant_test.sh`:
```bash
unzip -o "Датасет/eval.zip" -d eval_test/
cd eval_test/
chmod +x participant_test.sh
rm -f predictions.jsonl
./participant_test.sh \
  --images-dir ./queries \
  --manifest ./queries.tsv \
  --endpoint 'http://127.0.0.1:8080/v1/eval/predict' \
  --output ./predictions.jsonl
```

### Шаг 5: Проверка веб-интерфейса в браузере
Открыть в браузере `http://localhost:8080`:
1. Протестировать загрузку фото этикетки вин.
2. Проверить мгновенное открытие карточки вина и бейджа Роскачества (>83 баллов).
3. Протестировать диалог с AI-сомелье и рекомендации блюд.

---

## 3. Сильные стороны для презентации жюри РСХБ

1. **Enterprise-архитектура**: не монолитный скрипт на коленке, а масштабируемая микросервисная платформа финтех-уровня (DDD, Bounded Contexts, Gateway, Zero Secrets).
2. **Низкая задержка и надежность**: взаимодействие с моделью через **Redis Streams RPC** (задержка сети брокера < 1 мс) и гарантированная защита GPU от падений по памяти с помощью **Consumer Groups**.
3. **Бесшовная экосистема**: вход в 1 клик через **Яндекс ID OAuth 2.0** — идеальный пользовательский опыт в мобильной среде.
4. **Продуктовая ценность**: интеграция с «Винным гидом России» Роскачества, умный AI-сомелье с RAG и персонализированный «Винный шкаф» повышают лояльность и конверсию в покупку на платформе «Своё Вино».
