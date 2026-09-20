# 🍷 Руководство по интеграции API и WebSocket для Frontend-разработчика

Платформа **«Своё Вино»** — единый бэкенд и AI-сомелье для распознавания и подбора российских вин.

---

## 🌐 Базовые адреса и точки входа

| Сервис | URL | Описание |
| :--- | :--- | :--- |
| **API Gateway (HTTP)** | `http://localhost:8080` *(или `:8050`)* | Единая точка входа ко всем REST эндпоинтам |
| **Swagger UI / OpenAPI** | `http://localhost:8080/docs` | Интерактивная документация, схемы DTO и песочница |
| **OpenAPI JSON Спека** | `http://localhost:8080/openapi.json` | Спецификация для кодогенерации (OpenAPI Generator / Orval) |
| **WebSocket AI-Сомелье** | `ws://localhost:8080/ws/sommelier` | Двусторонний диалог, онбординг и подбор вин в реальном времени |
| **Интерактивный тестер WS** | `http://localhost:8080/ws/test` | Готовая страница для проверки сокета в браузере |
| **Чекер хакатона** | `POST http://localhost:8080/v1/eval/predict` | Регламентный эндпоинт тестирования (SLA < 1 сек) |

---

## 🔐 Аутентификация и режимы работы

### 1. Гостевой режим (без регистрации)
Используется для анонимных пользователей (до 5 бесплатных сканирований этикеток):
* Фронтенд генерирует один раз UUIDv4 фингерпринт устройства и сохраняет в `localStorage`:
  ```javascript
  const deviceFingerprint = localStorage.getItem('device_fp') || crypto.randomUUID();
  localStorage.setItem('device_fp', deviceFingerprint);
  ```
* Во все запросы к API передаётся заголовок:
  ```http
  X-Device-Fingerprint: <deviceFingerprint>
  ```
* В ответах на сканирование возвращается заголовок:
  ```http
  X-Scan-Limit-Remaining: 4
  ```
* При исчерпании лимита бэкенд возвращает **HTTP 402 Payment Required** с телом:
  ```json
  {
    "detail": "Бесплатный лимит сканирований (5) исчерпан. Пожалуйста, зарегистрируйтесь или войдите в аккаунт."
  }
  ```
  *Действие фронтенда:* показать модалку регистрации/входа или экран пейволла.

---

### 2. Авторизованный режим (JWT Bearer)
После входа или регистрации все защищенные запросы сопровождаются заголовком:
```http
Authorization: Bearer <access_token>
```

#### Эндпоинты авторизации (`/api/v1/auth`):

#### 1) Регистрация
`POST /api/v1/auth/register`
```json
// Request Body
{
  "email": "user@example.com",
  "password": "StrongPassword123!",
  "full_name": "Иван Виноделов"
}
```
```json
// Response 201 Created
{
  "id": "c1f7602e-9d7a-429f-8551-7f8a7e04f05c",
  "email": "user@example.com",
  "full_name": "Иван Виноделов",
  "is_admin": false,
  "created_at": "2026-09-20T12:00:00Z"
}
```

#### 2) Вход (Login)
`POST /api/v1/auth/login`
```json
// Request Body
{
  "email": "user@example.com",
  "password": "StrongPassword123!"
}
```
```json
// Response 200 OK
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "refresh_token": "d7a8f90b1c2e3d4...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 3) Обновление Access-токена (Refresh)
`POST /api/v1/auth/refresh`
```json
// Request Body
{
  "refresh_token": "d7a8f90b1c2e3d4..."
}
```
```json
// Response 200 OK
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "refresh_token": "e8b9a01c2d3e4f5...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### 4) Управление сессиями устройств (`/api/v1/sessions`):
* `GET /api/v1/sessions` — список активных устройств пользователя (ПК, телефон, планшет). Лимит по умолчанию: 5 устройств.
* `DELETE /api/v1/sessions/{id}` — удаленный отзыв конкретной сессии (например, завершить сессию на забытом планшете).
* `DELETE /api/v1/sessions` — завершить все сессии, кроме текущей (`revoke_all_except_current`).

---

## 🍇 Каталог вин и Вкусовая матрица (Taste Matrix)

### 1) Список вин с фильтрацией и пагинацией
`GET /api/v1/catalog/wines`

**Query-параметры:**
* `category` *(опционально)*: `Белое` \| `Красное` \| `Розовое` \| `Игристое`
* `region` *(опционально)*: `Крым`, `Кубань`, `Долина Дона`, `Дагестан` и др.
* `sugar_type` *(опционально)*: `Сухое` \| `Полусухое` \| `Полусладкое` \| `Сладкое` \| `Брют`
* `min_score` *(опционально)*: минимальный балл Роскачества (например, `80.0`)
* `query` *(опционально)*: полнотекстовый поиск по названию, винодельне или сорту винограда
* `limit` *(default: 20)*: количество элементов на странице
* `offset` *(default: 0)*: смещение для пагинации

**Пример ответа 200 OK:**
```json
{
  "items": [
    {
      "id": "0f8c74c9-9743-4b2e-945c-f23ba6cc9d81",
      "slug": "aligote-barrel-2024",
      "name": "Алиготе Баррель, 2024",
      "category": "Белое",
      "color_desc": "Светло-соломенный с золотистым отблеском",
      "region": "Кубань",
      "grape_varieties": ["Алиготе"],
      "winery": "Фанагория",
      "roskachestvo_score": 83.5,
      "sugar_type": "Сухое",
      "price_rub": 1250.0,
      "image_url": "/s3/catalog/aligote.webp",
      "sweetness": 1.1,
      "body": 3.2,
      "acidity": 4.1,
      "oak": 3.0
    }
  ],
  "total": 2103,
  "limit": 20,
  "offset": 0
}
```

> [!TIP]
> **Отображение радар-чарта вкуса (Taste Radar):**
> Поля `sweetness`, `body`, `acidity`, `oak` имеют нормализованную шкалу от `1.0` до `5.0`. Используйте их для отрисовки радарной диаграммы или полос органолептики.

---

### 2) Детальная карточка вина
`GET /api/v1/catalog/wines/{id_or_slug}`

Поддерживает как UUID (`0f8c74c9-...`), так и человекочитаемый слаг (`fanagoriya-100-ottenkov-krasnogo-saperavi`).

**Пример ответа 200 OK:**
```json
{
  "id": "5e8baa70-f357-443f-9872-85e9bfe36abd",
  "slug": "fanagoriya-100-ottenkov-saperavi",
  "name": "100 оттенков красного. Саперави",
  "category": "Красное",
  "color_desc": "Глубокий темно-рубиновый",
  "region": "Кубань",
  "winery": "Фанагория",
  "roskachestvo_score": 83.5,
  "sugar_type": "Сухое",
  "price_rub": 2400.0,
  "description": "Густое экстрактивное вино с тонами спелой вишни, чернослива и шоколада. Длительное послевкусие с нюансами дуба.",
  "vintage_year": 2021,
  "aroma_tags": ["черная смородина", "вишня", "чернослив", "дуб", "шоколад"],
  "flavor_tags": ["ягодный", "пряный", "танинный"],
  "sweetness": 1.2,
  "body": 4.8,
  "acidity": 3.2,
  "oak": 4.0,
  "pairings": [
    {
      "id": "a1b2c3d4-...",
      "food_category": "Мясо",
      "dish_name": "Стейк Рибай",
      "recommendation_reason": "Высокие бархатистые танины смягчают жирность мраморной говядины."
    }
  ]
}
```

---

### 3) Поиск похожих вин (Similar Wines)
`GET /api/v1/catalog/wines/{slug}/similar?limit=4`
Возвращает список ближайших вин в 4D-пространстве вкуса (та же категория, минимальное расстояние по сладости, телу, кислотности и дубу).

---

## 📸 Распознавание этикеток (Vision Scanner)

`POST /api/v1/scan`
* **Content-Type**: `multipart/form-data`
* **Параметры формы**:
  * `image`: файл изображения (jpg, png, webp, до 15 МБ).
* **Заголовки**: `X-Device-Fingerprint` (для гостей) или `Authorization: Bearer` (для авторизованных).

**Пример ответа 200 OK:**
```json
{
  "scan_id": "8e3c12a4-5678-4321-abcd-ef0123456789",
  "recognized": true,
  "confidence": 0.94,
  "wine": {
    "id": "5e8baa70-f357-443f-9872-85e9bfe36abd",
    "slug": "fanagoriya-100-ottenkov-saperavi",
    "name": "100 оттенков красного. Саперави",
    "category": "Красное",
    "winery": "Фанагория",
    "roskachestvo_score": 83.5,
    "image_url": "/s3/catalog/saperavi.webp"
  },
  "free_scans_remaining": 3
}
```

---

## 🍷 Винный погреб пользователя (User Cellar)

Все эндпоинты требуют авторизации `Bearer <token>`:

* `GET /api/v1/cellar` — список сохраненных вин в погребе.
* `POST /api/v1/cellar` — добавить вино в погреб:
  ```json
  {
    "wine_id": "5e8baa70-f357-443f-9872-85e9bfe36abd",
    "status": "in_cellar",  // "in_cellar" | "consumed" | "wishlist"
    "quantity": 2,
    "user_notes": "Куплено в поездке на винодельню",
    "user_rating": 5
  }
  ```
* `PATCH /api/v1/cellar/{item_id}` — обновить статус, количество или личную заметку.
* `DELETE /api/v1/cellar/{item_id}` — удалить вино из погреба.

---

## 🤖 WebSocket AI-Сомелье (`/ws/sommelier`)

Полноценный интерактивный ассистент с поддержкой двухфазной мгновенной отдачи карточек вин и потокового стриминга (Real-time UX).

### 1. Подключение:
```javascript
// Авторизованный режим:
const ws = new WebSocket(`ws://localhost:8080/ws/sommelier?token=${accessToken}`);

// Гостевой режим (без токена):
const ws = new WebSocket('ws://localhost:8080/ws/sommelier');
```

---

### 2. Исходящие сообщения (Client -> Server):

#### А. Отправка вопроса сомелье:
```json
{
  "type": "message",
  "content": "Посоветуй полнотелое красное вино к стейку рибай до 3000 рублей",
  "stream": true
}
```
> [!IMPORTANT]
> Передавайте `"stream": true`, чтобы включить потоковую генерацию. Время получения первого токена составляет **150–250 мс**!

#### Б. Ответ на вопрос онбординга (5 вопросов):
```json
{
  "type": "answer",
  "step": 1,
  "code": "category",
  "answer": "Красное"
}
```

#### В. Авторизация на лету (если сокет открыт гостем):
```json
{
  "type": "auth",
  "token": "<access_token>"
}
```

---

### 3. Входящие события (Server -> Client):

#### 1) `welcome` — Приветствие при подключении
Присылается сервером сразу после `onopen`. Если пользователь новый, содержит первый вопрос онбординга:
```json
{
  "type": "welcome",
  "message": "Приветствую! Я ваш цифровой AI-сомелье...",
  "question": {
    "step": 1,
    "code": "category",
    "question": "Какое вино вы предпочитаете чаще всего?",
    "options": ["Белое", "Красное", "Розовое", "Игристое"]
  }
}
```

#### 2) `candidates_ready` — Мгновенные карточки вин (Фаза 1: 15–25 мс)
Отправляется мгновенно после поиска в PostgreSQL до начала генерации текста. **Фронтенд может сразу отрендерить 3 карточки вин!**
```json
{
  "type": "candidates_ready",
  "candidates": [
    {
      "id": "5e8baa70-f357-443f-9872-85e9bfe36abd",
      "slug": "fanagoriya-100-ottenkov-saperavi",
      "name": "100 оттенков красного. Саперави",
      "category": "Красное",
      "region": "Кубань",
      "roskachestvo_score": 83.5,
      "body": 4.0,
      "sweetness": 1.2,
      "acidity": 3.0,
      "price_rub": null,
      "image_url": "/s3/catalog/saperavi.webp"
    }
  ]
}
```

#### 3) `stream_chunk` — Потоковый чанк текста (Фаза 2: стриминг)
```json
{
  "type": "stream_chunk",
  "content": "Для "
}
```

#### 4) `stream_end` — Завершение генерации
```json
{
  "type": "stream_end",
  "candidates": [ ... ]
}
```

#### 5) `message` — Полный ответ (при `"stream": false`)
```json
{
  "type": "message",
  "role": "assistant",
  "content": "К стейку рибай рекомендую обратить внимание на полнотелые красные вина Кубани...",
  "candidates": [ ... ]
}
```

#### 6) `answer_ack` — Подтверждение ответа онбординга
```json
{
  "type": "answer_ack",
  "step": 1,
  "code": "category",
  "answer": "Красное",
  "next_question": {
    "step": 2,
    "code": "sugar",
    "question": "Какой уровень сладости вам ближе?",
    "options": ["Сухое", "Полусухое", "Полусладкое", "Сладкое"]
  }
}
```

#### 7) `onboarding_complete` — Завершение 5 вопросов
```json
{
  "type": "onboarding_complete",
  "taste_profile": {
    "sweetness": 1.2,
    "body": 4.5,
    "acidity": 3.2,
    "oak": 3.8
  },
  "candidates": [ ... ]
}
```

---

## 🎯 Чекер хакатона (Predict Endpoint)

Для проверки валидатором стенда хакатона:
* **URL**: `POST http://localhost:8080/v1/eval/predict`
* **Формат запроса**: `multipart/form-data`, поле `image` (файл изображения).
* **Формат ответа**:
  ```json
  {
    "slug": "fanagoriya-100-ottenkov-krasnogo-saperavi"
  }
  ```
  *(или массив `[{"slug": "..."}]`)*
* **SLA по времени**: < 1000 мс.
