# 05. Руководство по прогону чекера хакатона (Evaluation Guide)

Организаторы хакатона ЛЦТ 2026 предоставили автоматизированный скрипт валидации сервиса в архиве `Датасет/eval.zip`: `participant_test.sh`.

---

## 1. Подготовка тестового окружения

Распакуйте содержимое `eval.zip` в рабочую директорию или тестовую папку:
```bash
unzip -o "Датасет/eval.zip" -d eval_test/
cd eval_test/
chmod +x participant_test.sh
```

В папке находятся:
- `participant_test.sh` — bash-скрипт тестирования;
- `queries.tsv` — манифест запросов (колонки: `query_id`, `image_path`);
- `queries/` — папка с тестовыми фотографиями вин (`019c68d0.jpg`, `02eef911.webp`, `096ca74e.jpg`).

---

## 2. Запуск чекера

Убедитесь, что стенд запущен (`docker compose up -d` в папке `infra/`).

Выполните команду проверки:
```bash
./participant_test.sh \
  --images-dir ./queries \
  --manifest ./queries.tsv \
  --endpoint 'http://127.0.0.1:8080/v1/eval/predict' \
  --output ./predictions.jsonl
```

> **Примечание**: если файл `predictions.jsonl` уже существует, скрипт завершится с ошибкой защиты от перезаписи. Перед повторным запуском удалите старый файл: `rm -f predictions.jsonl`.

---

## 3. Анализ результатов

Скрипт формирует файл `predictions.jsonl`, где каждая строка содержит результат проверки одного изображения:

```json
{"query_id":"q-000001","image_path":"019c68d0.jpg","image_sha256":"8d9c821e...","predicted_slug":"kokur-suhoe-2025","latency_ms":740}
{"query_id":"q-000002","image_path":"02eef911.webp","image_sha256":"4a7b912c...","predicted_slug":"aligote-barrel-2024","latency_ms":680}
{"query_id":"q-000003","image_path":"096ca74e.jpg","image_sha256":"1c3d559a...","predicted_slug":"avtohtonnoe-vino-kryma-beloe-suhoe","latency_ms":710}
```

Проверить валидность вывода:
```bash
# Просмотр всех предсказаний
jq . predictions.jsonl

# Проверка средней задержки (latency)
awk -F '"latency_ms":' '{print $2}' predictions.jsonl | tr -d '}' | awk '{sum+=$1; count++} END {print "Средняя задержка:", sum/count, "мс"}'
```

---

## 4. Ограничения и SLA чекера

1. **Таймаут**: скрипт делает `curl` с `--max-time 10` (10 секунд). Наш бэкенд настроен на внутренний таймаут `8.5 сек`, что гарантирует получение ответа до обрыва соединения клиентом.
2. **Формат ответа**: чекер принимает строгий JSON-объект `{"slug": "..."}` или массив `[{"slug": "..."}]`. При неудачном распознавании отдается `{"slug": null}`.
3. **Последовательный прогон**: чекер отправляет фотографии строго по одной, ожидая полного ответа перед отправкой следующей.
