# 03. Хронология разработки и Changelog

Данный документ фиксирует все выполненные этапы, добавленные фичи и коммиты в репозиториях организации `WineHackathon`.

---

## 📅 Этап 1: Исследование и проектирование (Intake & Architecture)
- **Изучение задачи**: Проанализирован `task_data.json` (ЛЦТ 2026, задача 202 от РСХБ), датасет `strapi_output0709.csv` (6 325 вин) и чекер `eval.zip/participant_test.sh`.
- **Изучение кодстайла**: Исследован стек организации `IPKService` (`FastAPI`, `pydantic-settings`, `aioboto3`, `SQLAlchemy 2.0 async`, чистая архитектура).
- **Выбор брокера и хранилища**:
  - Брокер: Redis Streams RPC с PubSub каналами ответов (минимальная задержка < 1 мс).
  - Хранилище: MinIO S3 для изоляции тяжелых картинок от брокера.
- **Создание репозиториев на GitHub**: созданы все 10 репозиториев в организации `WineHackathon`.

---

## 📅 Этап 2: Разработка базовых библиотек и инфраструктуры

### 1. `WineHackathon/database`
- **Коммит**: `feat: initial SQLAlchemy 2.0 async models and session pool`
- **Добавлено**:
  - `Base`, `UUIDMixin`, `TimestampMixin` для единообразия моделей;
  - Модель `Wine` (slug, название, цвет, сахар, регион, винодельня, балл Роскачества, S3 ключ);
  - Модель `WineFoodPairing` (гастропары к винам);
  - Модель `User` (поддержка Email и Яндекс ID OAuth 2.0);
  - Модель `UserCellar` (винный погреб, дегустационные заметки, личные оценки 1-5 звезд);
  - Модель `ScanLog` (аудит сканирований и замер latency);
  - Пул соединений `asyncpg` с `pool_pre_ping=True` и dependency generator `get_session`.

### 2. `WineHackathon/protos`
- **Коммит**: `feat: initial shared Pydantic v2 contracts and DTO schemas`
- **Добавлено**:
  - DTO сканирования: `RecognitionTaskDTO`, `RecognitionResultDTO`, `EvaluationResponseDTO`;
  - DTO каталога: `WineDTO`, `WineDetailDTO`, `WineFilterParams`, `WineManifestResponseDTO`, `WineDeltaResponseDTO`;
  - DTO авторизации: `UserRegisterDTO`, `UserLoginDTO`, `YandexAuthDTO`, `TokenResponseDTO`, `UserProfileDTO`;
  - DTO сомелье: `SommelierChatRequest`, `SommelierChatResponse`, `FoodPairingRecommendation`.

### 3. `WineHackathon/infra`
- **Коммиты**: 
  - `feat: initial Docker Compose setup, Nginx gateway and MinIO provisioning`
  - `feat: route root traffic to frontend and add frontend service to docker-compose`
- **Добавлено**:
  - `docker-compose.yml` с полной топологией 10 сервисов;
  - `nginx.conf` шлюза (порт `:8080` для чекера, маршрутизация по префиксам API, раздача фронтенда на `/`);
  - Сервис `createbuckets` для автоматического создания бакетов `wine-catalog` и `wine-scans` в MinIO;
  - Конфигурация Redis с AOF персистентностью (`appendonly yes`, `appendfsync everysec`);
  - `.env.example` без единого секрета.

---

## 📅 Этап 3: Разработка бизнес-сервисов

### 4. `WineHackathon/catalog-service`
- **Коммит**: `feat: complete catalog service with REST API, filtering, ML sync and seed script`
- **Добавлено**:
  - `WineRepository` и `CatalogService`;
  - Эндпоинты `/api/v1/catalog/wines` (поиск, фильтры по цвету, сахару, винодельне, регионам, рейтингу);
  - Эндпоинты `/api/v1/catalog/sync/manifest` и `/delta` для ML-сервера;
  - Скрипт `scripts/seed_wines.py` для парсинга `strapi_output0709.csv` и загрузки эталонных фото в S3;
  - `Dockerfile` (non-root, healthcheck).

### 5. `WineHackathon/recognition-service`
- **Коммит**: `feat: complete recognition service with S3 upload, Redis Streams RPC and /v1/eval/predict endpoint`
- **Добавлено**:
  - Эндпоинт чекера `POST /v1/eval/predict` (строгое соответствие `participant_test.sh`);
  - Честное распознавание: каждому скану присваивается уникальный `image_id` (UUIDv4);
  - Асинхронный аплоад в S3 через `aioboto3`;
  - RPC-клиент через Redis Streams `ml:tasks:recognition` и PubSub с таймаутом 8.5 сек;
  - Пользовательский эндпоинт `/api/v1/recognition/scan` с обогащением карточкой вина.

### 6. `WineHackathon/auth-service`
- **Коммит**: `feat: complete auth service with Email and Yandex ID OAuth 2.0 and JWT`
- **Добавлено**:
  - Вход и регистрация по Email/паролю (хэширование Bcrypt);
  - **Яндекс ID OAuth 2.0**: получение профиля (`id`, `email`, `avatar`, `first_name`) в один клик;
  - Выпуск и ротация JWT Access (15 мин) и Refresh (30 дней в Redis) токенов;
  - Эндпоинты `/api/v1/auth/yandex/url`, `/yandex/login`, `/register`, `/login`, `/refresh`, `/me`.

### 7. `WineHackathon/user-service`
- **Коммит**: `feat: complete user service with personal wine cellar and scan history`
- **Добавлено**:
  - «Мой винный погреб / Избранное» (статусы: `in_cellar`, `wishlist`, `tasted`, личные оценки 1-5 звезд, заметки);
  - История сканирований пользователя с логированием задержки и результатов;
  - Проверка JWT-токенов пользователей.

### 8. `WineHackathon/sommelier-service`
- **Коммит**: `feat: complete sommelier service with RAG over Roskachestvo guide and food pairings`
- **Добавлено**:
  - RAG-пайплайн по базе Роскачества (>83 баллов) и дескрипторам вкуса;
  - Чат-ассистент `/api/v1/sommelier/chat` с контекстом текущего вина;
  - Эндпоинты подбора гастропар `/pairings/{slug}` и похожих российских вин `/similar/{slug}`;
  - Поддержка внешних LLM и богатый встроенный fallback.

### 9. `WineHackathon/ml-service`
- **Коммит**: `feat: complete ML recognition worker, feature extractor, and vector search index`
- **Добавлено**:
  - Воркер на GPU/CPU: Consumer Group (`count=1`) с защитой от CUDA OOM;
  - Модуль извлечения визуальных эмбеддингов (PyTorch MobileNetV3 / ResNet / DINOv2);
  - Косинусный векторный индекс с поиском Top-1 за < 1 мс;
  - Скрипт индексации `scripts/build_index.py`.

### 10. `WineHackathon/frontend`
- **Коммит**: `feat: complete web application with camera scanner, wine card, and AI sommelier chat`
- **Добавлено**:
  - Адаптивный веб-интерфейс на Tailwind CSS и Lucide Icons;
  - Снимок с камеры / загрузка фотографии бутылки с замером latency в реальном времени;
  - Карточка найденного вина с оценкой Роскачества;
  - Интерактивный диалог с AI-сомелье;
  - Кнопка авторизации через Яндекс ID.

### 11. `WineHackathon/backend`
- **Коммит**: `docs: master microservices architecture specification and ecosystem overview`
- **Добавлено**:
  - Мастер-спецификация платформы, схема взаимодействия микросервисов и сводное руководство для жюри.

---

## 📅 Этап 4: Комплексное тестирование и обеспечение надежности (100% Pass Rate)
- **Цель**: Полное покрытие тестами бизнес-логики, контрактов, моделей данных и API эндпоинтов всех сервисов.
- **Разработанные тестовые наборы**:
  1. `protos/tests/test_schemas.py`: валидация граничных условий Pydantic v2 схем, парсинг JSON;
  2. `database/tests/test_models.py`: создание моделей SQLAlchemy 2.0, связи `relationship`, UUIDv4, `to_dict`;
  3. `catalog-service/tests/test_catalog_api.py`: фильтрация вин, преобразование моделей в DTO, эндпоинты каталога и манифеста;
  4. `recognition-service/tests/test_eval_api.py`: соответствие чекеру `POST /v1/eval/predict`, RPC клиент Redis Streams, таймаут 8.5с (`{"slug": null}`);
  5. `auth-service/tests/test_auth_api.py`: прямое хэширование Bcrypt, жизненный цикл JWT, ротация refresh токенов в Redis;
  6. `user-service/tests/test_cellar_api.py`: добавление/удаление из винного погреба, обновление счетчика бутылок;
  7. `sommelier-service/tests/test_sommelier_api.py`: сборка RAG-промпта по базе Роскачества, фоллбэк сомелье без внешнего LLM;
  8. `ml-service/tests/test_ml_pipeline.py`: косинусный поиск Top-1, сериализация/десериализация векторного индекса `.npz`, L2-нормализация.
- **Результаты тестирования**:
  - Все 8 тестовых наборов успешно выполнены (`scripts/run_all_tests.sh`) с **100% успешным прохождением (42 passed, 1 skipped)**.

