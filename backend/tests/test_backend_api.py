"""
Интеграционные тесты для единого входного клиента/шлюза backend:
- Чекер /v1/eval/predict (соответствие participant_test.sh)
- Пользовательский сканер /api/v1/ml/scan с защитой по X-Device-Fingerprint (лимит 5 сканов)
- Каталог /api/v1/catalog/wines
- Healthcheck /health
"""
import io
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from application.adapters.database.db_session import get_session
from application.dto.wine import WineDTO
from application.dto.user import UserDTO


@pytest.fixture
def mock_session():
    """Мок сессии базы данных для тестирования API без запущенного PostgreSQL."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def client(mock_session):
    """Тестовый клиент FastAPI с переопределенной зависимостью БД."""
    app.dependency_overrides[get_session] = lambda: mock_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_endpoint(client: TestClient):
    """Проверка доступности healthcheck эндпоинта."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "wine-backend-gateway"


def test_eval_predict_endpoint_success(client: TestClient):
    """Проверка соответствия /v1/eval/predict спецификации participant_test.sh."""
    fake_image = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    fake_image.name = "wine.jpg"

    with patch("application.adapters.ml.ml_dispatcher.MLDispatcher.predict", new_callable=AsyncMock) as mock_predict:
        mock_predict.return_value = ("shiraz-cru-2022", 0.96, 120)

        response = client.post(
            "/v1/eval/predict",
            files={"image": ("wine.jpg", fake_image, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "slug" in data
        assert data["slug"] == "shiraz-cru-2022"


def test_eval_predict_endpoint_fallback_null(client: TestClient):
    """Проверка /v1/eval/predict при низкой уверенности модели (возврат null)."""
    fake_image = io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
    fake_image.name = "wine.jpg"

    with patch("application.adapters.ml.ml_dispatcher.MLDispatcher.predict", new_callable=AsyncMock) as mock_predict:
        mock_predict.return_value = (None, 0.20, 95)

        response = client.post(
            "/v1/eval/predict",
            files={"image": ("wine.jpg", fake_image, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["slug"] is None


def test_anonymous_scan_rate_limiting(client: TestClient):
    """
    Проверка лимита в 5 бесплатных сканирований для анонимного пользователя
    по заголовку X-Device-Fingerprint и выдачи требования регистрации на 6-й скан.
    """
    fake_image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    fingerprint = "test-device-uuid-12345"

    with patch("application.adapters.redis.rate_limiter.ScanRateLimiter.check_and_increment", new_callable=AsyncMock) as mock_rate_limit, \
         patch("application.adapters.ml.ml_dispatcher.MLDispatcher.predict", new_callable=AsyncMock) as mock_predict, \
         patch("application.services.catalog_service.CatalogService.get_by_slug", new_callable=AsyncMock) as mock_get_slug:

        mock_predict.return_value = ("fanagoria-2020", 0.94, 150)
        mock_get_slug.return_value = None

        # 1-й - 5-й сканы: разрешены
        mock_rate_limit.return_value = (True, 4)  # (allowed, remaining)
        resp1 = client.post(
            "/api/v1/ml/scan",
            files={"image": ("wine.jpg", io.BytesIO(fake_image_bytes), "image/jpeg")},
            headers={"X-Device-Fingerprint": fingerprint},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["registration_required"] is False
        assert data1["remaining_scans"] == 4

        # 6-й скан: лимит исчерпан -> registration_required: True
        mock_rate_limit.return_value = (False, 0)
        resp6 = client.post(
            "/api/v1/ml/scan",
            files={"image": ("wine.jpg", io.BytesIO(fake_image_bytes), "image/jpeg")},
            headers={"X-Device-Fingerprint": fingerprint},
        )
        assert resp6.status_code == 200
        data6 = resp6.json()
        assert data6["registration_required"] is True
        assert data6["remaining_scans"] == 0


def test_sommelier_chat_unauthenticated_registration_required(client: TestClient):
    """
    Проверка требования регистрации для неавторизованного пользователя в чате сомелье.
    """
    payload = {
        "messages": [{"role": "user", "content": "Посоветуй белое сухое к рыбе"}]
    }
    resp = client.post("/api/v1/sommelier/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["registration_required"] is True
    assert "зарегистрируйтесь" in data["reply"].lower()


def test_sommelier_onboarding_unauthenticated_step5(client: TestClient):
    """
    Проверка пейволла на 5 шаге онбординга для неавторизованного пользователя.
    """
    payload = {
        "answer": {
            "step": 5,
            "code": "aromas",
            "answer": "Спелые ягоды и вишня"
        },
        "answers_history": {
            "category": "Красное",
            "sweetness": "Сухое",
            "body": "Плотное",
            "acidity": "Больше свежести"
        }
    }
    resp = client.post("/api/v1/sommelier/onboarding/answer", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] is True
    assert data["registration_required"] is True
    assert data["candidates"] == []


def test_token_type_confusion_rejection(client: TestClient):
    """
    Проверка защиты от Token Type Confusion (HIGH-05):
    Попытка использовать refresh_token вместо access_token для доступа к /api/v1/users/me
    должна отклоняться со статусом 401 Unauthorized.
    """
    from application.services.auth_service import TokenService
    import uuid

    token_service = TokenService()
    user_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id)

    # 1. Запрос с refresh_token должен быть отклонен (401)
    resp_refresh = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens.refresh_token}"},
    )
    assert resp_refresh.status_code == 401
    assert "авторизация" in resp_refresh.json()["detail"].lower()


def test_auth_refresh_endpoint_success_and_rejection(client: TestClient):
    """
    Проверка эндпоинта POST /api/v1/auth/refresh:
    - Обновление с валидным refresh_token возвращает 200 и новые токены.
    - Обновление с access_token отклоняется с кодом 401.
    """
    from application.services.auth_service import TokenService
    from application.adapters.database.models.user import User
    import uuid

    token_service = TokenService()
    user_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id)

    # 1. Попытка рефреша с access_token -> 401
    resp_bad = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens.access_token},
    )
    assert resp_bad.status_code == 401

    # 2. Успешный рефреш с моком пользователя в БД
    mock_user = User(
        id=user_id,
        email="sommelier.user@wine.ru",
        first_name="Сомелье",
        is_admin=False,
    )
    with patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_user
        resp_ok = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens.refresh_token},
        )
        assert resp_ok.status_code == 200
        data = resp_ok.json()
        assert "tokens" in data
        assert "user" in data
        assert data["user"]["email"] == "sommelier.user@wine.ru"
        assert data["tokens"]["access_token"] != ""


def test_wine_not_found_returns_404(client: TestClient):
    """Проверка возврата HTTP 404 при запросе несуществующего вина (WineNotFound)."""
    with patch("application.adapters.database.repositories.wine_repo.WineRepository.get_by_slug", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = client.get("/api/v1/catalog/wines/non-existent-wine-slug-12345")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data
        assert "не найдено" in data["detail"].lower()


def test_user_not_found_returns_404(client: TestClient):
    """Проверка возврата HTTP 404 при запросе профиля несуществующего пользователя (UserNotFound)."""
    from application.services.auth_service import TokenService
    token_service = TokenService()
    user_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id)

    with patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert resp.status_code == 404
        assert "не найден" in resp.json()["detail"].lower()


def test_cellar_item_not_found_returns_404(client: TestClient):
    """Проверка возврата HTTP 404 при удалении несуществующей позиции из погреба (CellarItemNotFound)."""
    from application.services.auth_service import TokenService
    token_service = TokenService()
    user_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id)
    item_id = uuid.uuid4()

    with patch("application.adapters.database.repositories.cellar_repo.CellarRepository.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = client.delete(
            f"/api/v1/users/cellar/{item_id}",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert resp.status_code == 404
        assert "не найдена" in resp.json()["detail"].lower()


def test_yandex_auth_url(client: TestClient):
    """Проверка эндпоинта получения URL авторизации Яндекс ID."""
    resp = client.get("/api/v1/auth/yandex/url")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "oauth.yandex.ru/authorize" in data["url"]
    assert "client_id" in data


def test_yandex_oauth_flow(client: TestClient):
    """Проверка авторизации через Яндекс ID (POST /api/v1/auth/yandex и GET /api/v1/auth/yandex/callback)."""
    # 1. POST /api/v1/auth/yandex с тестовым кодом
    with patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_yandex_id", new_callable=AsyncMock) as mock_get_ya, \
         patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_email", new_callable=AsyncMock) as mock_get_email, \
         patch("application.adapters.database.repositories.user_repo.UserRepository.save", new_callable=AsyncMock) as mock_save:
        mock_get_ya.return_value = None
        mock_get_email.return_value = None

        resp = client.post(
            "/api/v1/auth/yandex",
            json={"code": "test_code_123"},
            headers={"X-Device-Fingerprint": "fp_test_device_ya"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["email"] == "yandex_code_123@yandex.ru"
        assert data["tokens"]["access_token"] != ""

    # 2. GET /api/v1/auth/yandex/callback с параметром ?code=...
    with patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_yandex_id", new_callable=AsyncMock) as mock_get_ya, \
         patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_email", new_callable=AsyncMock) as mock_get_email, \
         patch("application.adapters.database.repositories.user_repo.UserRepository.save", new_callable=AsyncMock) as mock_save:
        mock_get_ya.return_value = None
        mock_get_email.return_value = None

        resp = client.get(
            "/api/v1/auth/yandex/callback?code=test_callback_456",
            headers={"X-Device-Fingerprint": "fp_test_device_ya_cb"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "user" in data
        assert "tokens" in data
        assert data["user"]["email"] == "yandex_callback_456@yandex.ru"


def test_register_with_device_fingerprint(client: TestClient):
    """Проверка привязки истории сканирований гостя при регистрации пользователя."""
    with patch("application.adapters.database.repositories.user_repo.UserRepository.get_by_email", new_callable=AsyncMock) as mock_get_email, \
         patch("application.adapters.database.repositories.user_repo.UserRepository.save", new_callable=AsyncMock) as mock_save, \
         patch("application.adapters.database.repositories.scan_repo.ScanRepository.link_guest_scans_to_user", new_callable=AsyncMock) as mock_link:
        mock_get_email.return_value = None
        mock_link.return_value = 3

        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "link.scans@example.com",
                "password": "secretpassword123",
                "first_name": "Тестер",
            },
            headers={"X-Device-Fingerprint": "guest_device_to_link_99"},
        )
        assert resp.status_code == 200
        assert mock_link.called
        assert mock_link.call_args[0][0] == "guest_device_to_link_99"


@pytest.mark.asyncio
async def test_ml_dispatcher_mock_mode():
    """Проверка работы MLDispatcher в режиме mock_mode при отсутствии внешнего воркера."""
    from application.adapters.ml.ml_dispatcher import MLDispatcher
    dispatcher = MLDispatcher(redis_client=None)

    slug, confidence, latency_ms = await dispatcher.predict(b"fake_image_bytes")
    assert slug == "fanagoriya-100-ottenkov-krasnogo-kaberne-kaberne-sovinon-krasnoe-suhoe-135"
    assert confidence == 0.94
    assert latency_ms >= 0


def test_logout_flow(client: TestClient):
    """Проверка эндпоинта /logout с отзывом токенов через Redis blacklist."""
    from application.services.auth_service import TokenService
    token_service = TokenService()
    user_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id)

    mock_redis = AsyncMock()
    mock_redis.setex = AsyncMock()
    from backend.app.dependencies import get_redis_client
    app.dependency_overrides[get_redis_client] = lambda: mock_redis

    try:
        resp = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens.refresh_token},
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "успешный выход" in data["message"].lower()

        # Проверяем, что оба токена были отправлены в черный список Redis
        assert mock_redis.setex.call_count == 2
    finally:
        app.dependency_overrides.pop(get_redis_client, None)


def test_user_sessions_endpoints(client: TestClient):
    """Проверка эндпоинтов управления активными сессиями пользователя (/api/v1/users/sessions)."""
    from application.services.auth_service import TokenService
    from application.adapters.database.models.user_session import UserSession
    from datetime import datetime, timezone

    token_service = TokenService()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id, session_id=session_id)

    mock_session_obj = UserSession(
        id=session_id,
        user_id=user_id,
        refresh_token_hash="fake_hash",
        device_name="Chrome на macOS",
        created_at=datetime.now(timezone.utc),
        last_active_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )

    with patch("application.adapters.database.repositories.session_repo.SessionRepository.list_by_user_id", new_callable=AsyncMock) as mock_list, \
         patch("application.adapters.database.repositories.session_repo.SessionRepository.delete_by_id", new_callable=AsyncMock) as mock_del, \
         patch("application.adapters.database.repositories.session_repo.SessionRepository.delete_by_user_id_except", new_callable=AsyncMock) as mock_del_except:

        mock_list.return_value = [mock_session_obj]
        mock_del.return_value = True
        mock_del_except.return_value = 2

        # 1. GET /api/v1/users/sessions
        resp = client.get(
            "/api/v1/users/sessions",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == str(session_id)
        assert data[0]["is_current"] is True
        assert data[0]["device_name"] == "Chrome на macOS"

        # 2. DELETE /api/v1/users/sessions/{session_id}
        with patch("application.adapters.database.repositories.session_repo.SessionRepository.get_by_id", new_callable=AsyncMock) as mock_get_by_id:
            mock_get_by_id.return_value = mock_session_obj
            resp_del = client.delete(
                f"/api/v1/users/sessions/{session_id}",
                headers={"Authorization": f"Bearer {tokens.access_token}"},
            )
            assert resp_del.status_code == 200
            del_data = resp_del.json()
            assert del_data["status"] == "ok"
            assert del_data["revoked_session_id"] == str(session_id)

        # 3. DELETE /api/v1/users/sessions (revoke other sessions)
        resp_del_all = client.delete(
            "/api/v1/users/sessions",
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert resp_del_all.status_code == 200
        all_data = resp_del_all.json()
        assert all_data["status"] == "ok"
        assert all_data["revoked_count"] == 2


def test_submit_onboarding_answer_flat_format(client: TestClient):
    """Проверка отправки ответа онбординга в удобном плоском формате (без вложенного 'answer')."""
    payload = {
        "step": 1,
        "code": "category",
        "answer": "Белое",
        "answers_history": {}
    }
    resp = client.post("/api/v1/sommelier/onboarding/answer", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_step"] == 1
    assert data["completed"] is False
    assert data["next_question"] is not None
    assert "sweetness" in data["next_question"]["code"]


def test_add_to_cellar_by_slug(client: TestClient):
    """Проверка добавления вина в погреб по wine_slug вместо wine_id."""
    from application.services.auth_service import TokenService
    from application.adapters.database.models.wine import Wine
    from application.adapters.database.models.cellar import UserCellar, CellarStatus

    token_service = TokenService()
    user_id = uuid.uuid4()
    tokens = token_service.create_token_pair(user_id)

    from application.entities.wine_categories import WineCategory, SugarType
    mock_wine = Wine(
        id=uuid.uuid4(),
        name="Шато Ле Гран Восток",
        slug="chateau-le-grand-vostok",
        category=WineCategory.WHITE,
        color_desc="Белое",
        sugar_type=SugarType.DRY,
        region="Кубань",
        grape_varieties=["Совиньон Блан"],
        description="Свежее белое вино",
        winery="Chateau Le Grand Vostok",
    )

    with patch("application.adapters.database.repositories.wine_repo.WineRepository.get_by_slug", new_callable=AsyncMock) as mock_get_slug, \
         patch("application.adapters.database.repositories.cellar_repo.CellarRepository.get_by_user_and_wine", new_callable=AsyncMock) as mock_get_existing, \
         patch("application.adapters.database.repositories.cellar_repo.CellarRepository.save", new_callable=AsyncMock) as mock_save:

        mock_get_slug.return_value = mock_wine
        mock_get_existing.return_value = None

        payload = {
            "wine_slug": "chateau-le-grand-vostok",
            "status": "wishlist",
            "bottles_count": 2,
            "tasting_notes": "Купить к празднику"
        }
        resp = client.post(
            "/api/v1/users/cellar",
            json=payload,
            headers={"Authorization": f"Bearer {tokens.access_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["wine_id"] == str(mock_wine.id)
        assert data["status"] == "wishlist"
        assert data["bottles_count"] == 2







