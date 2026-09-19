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

    with patch("backend.app.services.ml_dispatcher.MLDispatcher.predict", new_callable=AsyncMock) as mock_predict:
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

    with patch("backend.app.services.ml_dispatcher.MLDispatcher.predict", new_callable=AsyncMock) as mock_predict:
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

    with patch("backend.app.services.rate_limiter.ScanRateLimiter.check_and_increment", new_callable=AsyncMock) as mock_rate_limit, \
         patch("backend.app.services.ml_dispatcher.MLDispatcher.predict", new_callable=AsyncMock) as mock_predict, \
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



