# Walkthrough: Модульный монорепозиторий WineHackathon & Вкусовая матрица

Реализована архитектурная реорганизация платформы в **модульный монорепозиторий** в соответствии со стандартом `Архив (2)/telegram/applications`, критерием хакатона **«Архитектура (15/100) — качество разделения функционала внутри репозитория, воспроизводимость»** и требованиями продуктовых сценариев.

---

## 🏛 1. Архитектура модульного монорепозитория

Проект разделен на 5 высокосвязных доменных слоев:

1. **[`application/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/application)**:
   - **`adapters/database/`**:
     - [`db_session.py`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/application/adapters/database/db_session.py): пул соединений `asyncpg`, фабрика асинхронных сессий.
     - [`transaction_manager.py`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/application/adapters/database/transaction_manager.py): атомарное управление транзакциями через `async with TransactionManager(session):`.
     - [`models/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/application/adapters/database/models/): `Wine` с вкусовой матрицей, `User` с `taste_profile`, `UserCellar`, `WineFoodPairing`, `UserScanHistory`, `UserPreferenceHistory`.
     - [`repositories/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/application/adapters/database/repositories/): `WineRepository`, `UserRepository`, `CellarRepository`, `ScanRepository`, `PreferenceRepository`.
   - **`dto/`**: Pydantic v2 контракты данных (`WineDTO`, `WineDetailDTO`, `TasteMatrixDTO`, `CellarItemDTO`, `UserDTO`, `ScanResultDTO`, `OnboardingStateDTO`).
   - **`services/`**: прикладная бизнес-логика (`CatalogService`, `UserService`, `CellarService`, `TasteProfileService`, `AuthService`).

2. **[`backend/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/backend)**:
   - Единый FastAPI клиент / API Gateway / BFF.
   - Эндпоинты:
     - `POST /v1/eval/predict`: чекер хакатона (`participant_test.sh`).
     - `POST /api/v1/ml/scan`: пользовательский сканер с защитой по `X-Device-Fingerprint` + IP (лимит 5 сканов для анонимов).
     - `GET /api/v1/catalog/wines`, `/api/v1/catalog/wines/{slug}`, `/api/v1/catalog/regions`.
     - `GET /api/v1/users/me`, `/api/v1/users/cellar`, `/api/v1/users/scans`.
     - `POST /api/v1/auth/register`, `/api/v1/auth/login`.
     - `POST /api/v1/sommelier/onboarding/answer`, `POST /api/v1/sommelier/chat`.

3. **[`sommelier/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/sommelier)**:
   - Специализированный микросервис AI-Сомелье.
   - **WebSocket-эндпоинт (`/ws/sommelier`)** для интерактивного диалога в реальном времени.
   - Сценарий «Оптимальный первый диалог» (5 базовых вопросов + адаптивные ветвления).
   - Движок подбора вин [`SommelierRecommendationEngine`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/sommelier/app/services/recommendation_engine.py) (4D расстояние вкуса + Jaccard по тегам).

4. **[`ml/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/ml)**:
   - Выделенный ML-слой: MobileNetV3 экстрактор признаков, векторный индекс `VectorIndex` с криптографической HMAC-SHA256 подписью, воркер очередей Redis Streams.

5. **[`infrastructure/`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/infrastructure)**:
   - Единый [`docker-compose.yml`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/infrastructure/docker-compose.yml).
   - Nginx Gateway [`nginx.conf`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/infrastructure/gateway/nginx.conf) с поддержкой WebSocket Upgrade (`Upgrade $http_upgrade; Connection "Upgrade";`).
   - Скрипт разметки вкусовой матрицы [`enrich_taste_matrix.py`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/infrastructure/scripts/enrich_taste_matrix.py).

---

## 🍇 2. Вкусовая матрица (Taste Matrix)

В модель `Wine` добавлены поля:
- `sweetness`: 1.0 (очень сухое) ... 5.0 (десертное).
- `body`: 1.0 (лёгкое) ... 5.0 (полнотелое/мощное).
- `acidity`: 1.0 (мягкая) ... 5.0 (хрустящая/свежая).
- `oak`: 1.0 (без дуба/сталь) ... 5.0 (выдержка в дубовых барриках).
- `aroma_tags`: список ароматических дескрипторов.
- `flavor_tags`: список вкусовых дескрипторов.
- `derived_attributes_confidence`: точность извлечения (от 0.0 до 1.0).

---

## 🧪 3. Результаты тестирования

Все тесты монорепозитория успешно пройдены (100%):
- `application/tests`: 5 passed
- `backend/tests`: 4 passed
- `sommelier/tests`: 3 passed
- `ml/tests`: 2 passed
- `protos/tests`: 5 passed
- `database/tests`: 3 passed
- `catalog-service/tests`: 9 passed
- `recognition-service/tests`: 8 passed
- `auth-service/tests`: 6 passed
- `user-service/tests`: 8 passed
- `sommelier-service/tests`: 5 passed
- `ml-service/tests`: 7 passed

**Итого: 65 тестов успешно пройдены (0 ошибок)!**

---

## 📚 4. Документация

Созданы подробные документы с русскоязычными комментариями и схемами:
- [`docs/ARCHITECTURE.md`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/docs/ARCHITECTURE.md)
- [`docs/ADR-002-MODULAR-MONOREPO.md`](file:///Users/ivanlesnyh/Desktop/%D1%85%D0%B0%D0%BA%D0%B0%D1%82%D0%BE%D0%BD%20%D0%BB%D1%86%D1%82/docs/ADR-002-MODULAR-MONOREPO.md)
