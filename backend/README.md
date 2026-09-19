# WineHackathon — Платформа «Своё Вино» & AI-Сомелье

Платформа цифрового сканирования этикеток российских вин и интеллектуального сомелье, разработанная для **Международного хакатона ЛЦТ 2026** (задача №202) в партнерстве с **РСХБ** и **«Винным гидом России» Роскачества**.

---

## 🏛 Системная архитектура (Enterprise Microservices)

Проект построен по стандартам **Clean Architecture**, **Domain-Driven Design (DDD)** и спецификации безопасности **Zero Secrets**.

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

## 📦 Репозитории экосистемы `WineHackathon`

| Репозиторий | Назначение | Стек |
| :--- | :--- | :--- |
| **[`infra`](https://github.com/WineHackathon/infra)** | Оркестрация стенда, Nginx Gateway, PostgreSQL 16, Redis 7 (AOF), MinIO (S3) | Docker Compose, Nginx Alpine |
| **[`database`](https://github.com/WineHackathon/database)** | Базовые модели SQLAlchemy 2.0 async, пул `asyncpg`, миграции Alembic | Python 3.11+, SQLAlchemy 2.0, asyncpg |
| **[`protos`](https://github.com/WineHackathon/protos)** | DTO схемы и Pydantic v2 контракты межсервисного взаимодействия | Pydantic v2 |
| **[`recognition-service`](https://github.com/WineHackathon/recognition-service)** | Эндпоинт чекера `/v1/eval/predict`, асинхронный S3 аплоад, Redis Streams RPC | FastAPI, aioboto3, redis.asyncio |
| **[`catalog-service`](https://github.com/WineHackathon/catalog-service)** | Мастер-каталог 6 325 вин «Своё Вино», фильтры, поиск, Sync API для ML | FastAPI, SQLAlchemy 2.0, PostgreSQL |
| **[`auth-service`](https://github.com/WineHackathon/auth-service)** | Аутентификация по Email/паролю и **Яндекс ID OAuth 2.0**, ротация JWT в Redis | FastAPI, httpx (Yandex API), bcrypt, pyjwt |
| **[`user-service`](https://github.com/WineHackathon/user-service)** | Личный кабинет, винный погреб / вишлист, дегустационные заметки и история сканов | FastAPI, SQLAlchemy 2.0, PostgreSQL |
| **[`sommelier-service`](https://github.com/WineHackathon/sommelier-service)** | AI-сомелье с RAG-контекстом по базе Роскачества и подбор гастропар | FastAPI, RAG Engine, LLM API |
| **[`ml-service`](https://github.com/WineHackathon/ml-service)** | Воркер распознавания на GPU, детекция этикетки, DINOv2 эмбеддинги, поиск FAISS | PyTorch, torchvision, FAISS, Redis Consumer |
| **[`frontend`](https://github.com/WineHackathon/frontend)** | Веб-приложение со сканером камеры, карточкой вина, входом через Яндекс и чатом | HTML5, Tailwind CSS, Lucide Icons |

---

## ⚡ Особенности реализации для чекера хакатона

1. **Строгое соответствие контракту чекера**:
   Сервис предоставляет эндпоинт `POST /v1/eval/predict`, принимающий multipart-поле `image` и возвращающий `{"slug": "..."}`.
2. **Сверхнизкая задержка (Sub-second Latency)**:
   - Взаимодействие с ML-воркером через **Redis Streams & PubSub** (оверхед брокера < 1 мс).
   - Защита по таймауту: `asyncio.wait_for(..., timeout=8.5s)` (в рамках 10-секундного лимита чекера).
   - Честное распознавание: каждому изображению присваивается уникальный `image_id` (UUIDv4) без подделки кэша.
3. **Защита GPU от перегрузки (Backpressure)**:
   Воркеры обрабатывают задачи через **Consumer Groups** (`XREADGROUP count=1`), гарантируя, что видеокарта никогда не упадет с ошибкой `CUDA Out of Memory`.
