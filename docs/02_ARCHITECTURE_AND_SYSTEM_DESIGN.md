# 02. Архитектура и системный дизайн

## 1. Архитектурные принципы
- **Clean Architecture & DDD**: четкое разграничение на Bounded Contexts (Авторизация, Каталог, Сканирование, Пользователи, AI-сомелье, ML-инференс).
- **Zero Secrets**: полное отсутствие захардкоженных секретов. Все параметры считываются через `pydantic-settings` и переменные окружения.
- **Defense in Depth**: СУБД (PostgreSQL 16) и брокер (Redis 7) изолированы во внутренней закрытой сети Docker `backend-net`, наружу выставлен исключительно порт шлюза Nginx (`:8080`).
- **Resilience & Backpressure**: Защита GPU от падения с `CUDA Out Of Memory` с помощью очередей Redis Streams и пула воркеров Consumer Groups.

---

## 2. Карта микросервисов в организации `WineHackathon`

```
                                    [ КЛИЕНТЫ ]
                      Web App (SPA)  │      │  participant_test.sh (Чекер)
                                     ▼      ▼
                   ┌──────────────────────────────────────────────┐
                   │             API GATEWAY (Nginx)              │
                   │  Порт :8080 (Чекер) & :80 / :443 (Web App)   │
                   └──────────────────────┬───────────────────────┘
                                          │
    ┌────────────────┬────────────────────┼───────────────────┬────────────────┐
    │ /api/v1/auth   │ /v1/eval & /scan   │ /api/v1/catalog   │ /api/v1/users  │ /api/v1/sommelier
    ▼                ▼                    ▼                   ▼                ▼
┌──────────────┐ ┌────────────────────┐ ┌─────────────────┐ ┌────────────┐ ┌───────────────────┐
│ AUTH SERVICE │ │RECOGNITION SERVICE │ │ CATALOG SERVICE │ │USER SERVICE│ │ SOMMELIER SERVICE │
│ - Email/Pass │ │ - Чекер хакатона   │ │ - 6325 вин      │ │ - Винный   │ │ - RAG Роскачество │
│ - Яндекс ID  │ │ - S3 аплоад        │ │ - Сорта, регионы│ │   погреб   │ │ - AI-дегустация   │
│ - JWT Tokens │ │ - Redis Stream RPC │ │ - Sync API (ML) │ │ - Заметки  │ │ - Гастропары      │
└──────────────┘ └─────────┬──────────┘ └─────────────────┘ └────────────┘ └───────────────────┘
                           │ Redis Stream (ml:tasks:recognition)
                           ▼
                 ┌────────────────────┐
                 │     ML SERVICE     │ (Выделенный GPU-сервер)
                 │ - DINOv2 / OCR     │
                 │ - FAISS Вектор. БД │
                 └────────────────────┘
```

---

## 3. Репозитории и технологии

1. **`WineHackathon/infra`**:
   - Docker Compose оркестрация: Nginx Gateway, MinIO S3, Redis 7 (с персистентностью AOF), PostgreSQL 16.
2. **`WineHackathon/database`**:
   - Общий пакет моделей SQLAlchemy 2.0 async, пул `asyncpg` (`pool_size=20`, `pool_pre_ping=True`), Alembic.
   - Модели: `Wine`, `WineFoodPairing`, `User`, `UserCellar`, `ScanLog`.
3. **`WineHackathon/protos`**:
   - Схемы Pydantic v2 и DTO для межсервисного взаимодействия.
4. **`WineHackathon/recognition-service`**:
   - Изолированный высоконадежный сканер: `POST /v1/eval/predict`, асинхронный S3 аплоад, Redis Streams RPC с таймаутом 8.5 сек.
5. **`WineHackathon/catalog-service`**:
   - Каталог 6 325 вин, фильтрация по сахару, цвету, региону, винодельне, Sync API для ML-сервера.
6. **`WineHackathon/auth-service`**:
   - Email/Password регистрация и вход, **Яндекс ID OAuth 2.0**, JWT Access (15 мин) и Refresh (30 дней) в Redis.
7. **`WineHackathon/user-service`**:
   - Винный погреб пользователя, вишлист, дегустационные заметки, история сканирований.
8. **`WineHackathon/sommelier-service`**:
   - AI-сомелье с RAG по базе Роскачества, подбор гастропар и похожих российских вин.
9. **`WineHackathon/ml-service`**:
   - Воркер инференса на GPU: Consumer Group (`count=1`), PyTorch feature extractor, косинусный поиск Top-1 за < 1 мс.
10. **`WineHackathon/frontend`**:
    - Web SPA (Tailwind CSS, Lucide Icons) со сканером камеры, карточкой вина и чатом сомелье.

---

## 4. Паттерн передачи изображений и Request-Reply через Redis

1. Входящий запрос чекера хакатона `POST /v1/eval/predict` принимает multipart-поле `image`.
2. Бэкенд генерирует `image_id = uuid4()`, сохраняет файл в S3 (`wine-scans/{image_id}.jpg`).
3. Бэкенд отправляет компактную задачу в Redis Stream `ml:tasks:recognition`:
   ```json
   {
     "request_id": "req_123",
     "image_id": "img_abc",
     "s3_key": "scans/img_abc.jpg"
   }
   ```
4. ML-воркер считывает задачу из потока, загружает картинку из S3, выполняет инференс (DINOv2 / FAISS).
5. ML-воркер публикует ответ в Redis PubSub канал `ml:results:{request_id}`:
   ```json
   {
     "request_id": "req_123",
     "slug": "kokur-suhoe-2025",
     "confidence": 0.94
   }
   ```
6. Бэкенд возвращает ответ клиенту чекера: `{"slug": "kokur-suhoe-2025"}`. Задержка сети брокера составляет менее 1 мс.
