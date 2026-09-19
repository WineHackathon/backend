# 04. Карта API и интеграций

Все внешние запросы проходят через **API Gateway (Nginx)** на порту `:8080`.

---

## 🎯 1. Чекер хакатона (Evaluation Harness)

### `POST /v1/eval/predict`
- **Назначение**: Основной эндпоинт тестирования чекером организаторов (`participant_test.sh`).
- **Content-Type**: `multipart/form-data`
- **Параметры**:
  - `image`: файл изображения бутылки/этикетки (binary).
- **Ответ (`200 OK`)**:
  ```json
  {
    "slug": "kokur-suhoe-2025"
  }
  ```
  *(Если этикетка не распознана: `{"slug": null}`)*.
- **SLA**: ответ < 1.5 сек (максимальный таймаут чекера 10 сек).

---

## 🍷 2. Каталог вин (`catalog-service`)

### `GET /api/v1/catalog/wines`
- **Параметры query**:
  - `query`: текстовый поиск по названию, винодельне или описанию.
  - `category`: фильтр категории (`Белое`, `Красное`, `Розовое`, `Игристое`).
  - `region`: регион (`Крым`, `Кубань`, `Долина Дона`, etc.).
  - `winery`: наименование производителя.
  - `sugar_type`: содержание сахара (`Сухое`, `Полусухое`, `Полусладкое`, `Сладкое`, `Брют`).
  - `min_score`: минимальный балл Роскачества (например, `83.0`).
  - `limit`: количество записей (default: 20).
  - `offset`: смещение (default: 0).
- **Ответ (`200 OK`)**:
  ```json
  {
    "total": 6325,
    "limit": 20,
    "offset": 0,
    "items": [
      {
        "id": "uuid",
        "slug": "aligote-barrel-2024",
        "name": "Алиготе Баррель, 2024",
        "category": "Белое",
        "color_desc": "Золотистый",
        "region": "Крым",
        "grape_varieties": ["Алиготе"],
        "winery": "Коммуналка",
        "roskachestvo_score": 84.0,
        "sugar_type": "Сухое",
        "price_rub": null,
        "image_url": "http://localhost:8080/s3/wine-catalog/catalog/DSC09173.webp"
      }
    ]
  }
  ```

### `GET /api/v1/catalog/wines/{slug}`
- **Параметры path**: `slug` вина.
- **Ответ (`200 OK`)**: детальная карточка вина со списком гастропар (`pairings`) и описанием.

### `GET /api/v1/catalog/wines/regions`
- **Ответ**: список всех уникальных регионов виноделия.

### `GET /api/v1/catalog/wines/wineries`
- **Ответ**: список всех производителей и виноделен.

### `GET /api/v1/catalog/sync/manifest`
- **Назначение**: отдает полный список всех вин для векторной индексации ML-сервером.

### `GET /api/v1/catalog/sync/delta?since={iso_timestamp}`
- **Назначение**: отдает вина, добавленные или обновленные после указанной даты.

---

## 🔐 3. Аутентификация и Яндекс ID (`auth-service`)

### `GET /api/v1/auth/yandex/url`
- **Ответ**: `{ "authorization_url": "https://oauth.yandex.ru/authorize?..." }` для редиректа на форму согласия Яндекс ID.

### `POST /api/v1/auth/yandex/login`
- **Тело запроса**:
  ```json
  { "code": "yandex_auth_code_from_callback" }
  ```
- **Ответ (`200 OK`)**:
  ```json
  {
    "user": {
      "id": "uuid",
      "email": "user@yandex.ru",
      "first_name": "Иван",
      "avatar_url": "https://avatars.yandex.net/..."
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIs...",
      "refresh_token": "uuid",
      "token_type": "bearer",
      "expires_in": 900
    }
  }
  ```

### `POST /api/v1/auth/register` & `POST /api/v1/auth/login`
- Регистрация и вход по Email + Password.

### `POST /api/v1/auth/refresh`
- Ротация refresh-токена и получение нового access-токена.

### `GET /api/v1/auth/me`
- **Headers**: `Authorization: Bearer <access_token>`
- **Ответ**: профиль текущего авторизованного пользователя.

---

## 🗄 4. Винный погреб и история (`user-service`)

### `GET /api/v1/users/cellar`
- **Headers**: `Authorization: Bearer <token>`
- **Query**: `status` (`in_cellar`, `wishlist`, `tasted`).
- **Ответ**: список вин в коллекции пользователя с личными оценками и заметками.

### `POST /api/v1/users/cellar`
- **Тело запроса**:
  ```json
  {
    "wine_id": "uuid",
    "status": "in_cellar",
    "bottles_count": 2,
    "personal_rating": 5,
    "tasting_notes": "Прекрасный винтаж, открыть к празднику."
  }
  ```

### `DELETE /api/v1/users/cellar/{item_id}`
- Удаление позиции из винного шкафа.

### `GET /api/v1/users/scans`
- История ранее отсканированных бутылок пользователем.

---

## 🤖 5. AI-Сомелье и Гастропары (`sommelier-service`)

### `POST /api/v1/sommelier/chat`
- **Тело запроса**:
  ```json
  {
    "messages": [
      { "role": "user", "content": "Какое блюдо лучше всего приготовить к этому вину?" }
    ],
    "context_wine_slug": "aligote-barrel-2024"
  }
  ```
- **Ответ**:
  ```json
  {
    "reply": "К вину «Алиготе Баррель, 2024» прекрасно подойдет сибас на гриле или молодые козьи сыры...",
    "recommended_slugs": ["aligote-barrel-2024", "kokur-suhoe-2025"],
    "food_pairings": ["Рыба и морепродукты"]
  }
  ```

### `GET /api/v1/sommelier/pairings/{slug}`
- Получение списка рекомендованных гастропар для выбранного вина.

### `GET /api/v1/sommelier/similar/{slug}`
- Рекомендации альтернативных российских вин со схожим вкусовым профилем.
