"""
Тесты специализированного сервиса sommelier:
- Онбординг из 5 вопросов
- Адаптивные ветки вопросов (красное -> дуб/плотность, белое -> кислотность/минеральность)
- Подбор по вкусовой матрице (Recommendation Engine)
- WebSocket диалог (/ws/sommelier)
"""
import pytest
from fastapi.testclient import TestClient

from sommelier.app.main import app
from sommelier.app.services.onboarding_service import SommelierOnboardingService
from sommelier.app.services.recommendation_engine import SommelierRecommendationEngine


import uuid
from application.services.token_service import TokenService


def test_onboarding_adaptive_questions():
    """Проверка адаптивности вопросов онбординга."""
    service = SommelierOnboardingService()

    # Шаг 1: Пользователь выбирает Красное вино
    q1 = service.get_question(step=1)
    assert q1.code == "category"

    # Шаг 3 для Красного: адаптивный вопрос про дуб и плотность
    q3_red = service.get_adaptive_question(step=3, answers={"category": "Красное"})
    assert "плотн" in q3_red.question.lower() or "дуб" in q3_red.question.lower()

    # Шаг 4 для Белого: адаптивный вопрос про кислотность и минеральность
    q4_white = service.get_adaptive_question(step=4, answers={"category": "Белое"})
    assert "кислотн" in q4_white.question.lower() or "минеральн" in q4_white.question.lower()

    # Шаг 5: необычное без указания региона -> вопрос про автохтоны и терруары
    q5_unusual = service.get_adaptive_question(step=5, answers={"aromas": "Редкие и необычные вкусы (автохтоны, петнаты)"})
    assert "автохтон" in q5_unusual.question.lower()
    assert "терруар" in q5_unusual.question.lower()

    # Шаг 5: необычное с уже выбранным регионом -> вопрос про автохтоны без повторного вопроса о регионе
    q5_unusual_with_region = service.get_adaptive_question(step=5, answers={
        "region": "Крым",
        "aromas": "Редкие и необычные вкусы (автохтоны, петнаты)",
    })
    assert "автохтон" in q5_unusual_with_region.question.lower()
    assert "терруар" not in q5_unusual_with_region.question.lower()


def test_recommendation_engine_scoring():
    """Проверка ранжирования вин по вкусовой матрице (4D расстояние вкуса + сходство ароматов)."""
    engine = SommelierRecommendationEngine()

    mock_wines = [
        {
            "slug": "wine-heavy-red",
            "name": "Тяжелое красное выдержанное",
            "category": "Красное",
            "sweetness": 1.2,
            "body": 4.8,
            "acidity": 2.8,
            "oak": 4.5,
            "aroma_tags": ["вишня", "дуб", "ваниль", "шоколад"],
        },
        {
            "slug": "wine-crisp-white",
            "name": "Свежее легкое белое",
            "category": "Белое",
            "sweetness": 1.1,
            "body": 1.8,
            "acidity": 4.6,
            "oak": 1.0,
            "aroma_tags": ["цитрус", "зеленое яблоко", "минералы"],
        },
    ]

    # Ищем плотное красное вино с ароматами вишни и дуба
    ranked = engine.rank_candidates(
        candidates=mock_wines,
        target_sweetness=1.2,
        target_body=4.5,
        target_acidity=3.0,
        target_oak=4.0,
        target_aromas=["вишня", "дуб"],
    )

    assert len(ranked) == 2
    # Первым должно идти вино с наименьшим расстоянием
    assert ranked[0]["slug"] == "wine-heavy-red"


def test_sommelier_websocket_guest_paywall():
    """Проверка пейволла для гостей (registration_required: True)."""
    client = TestClient(app)
    with client.websocket_connect("/ws/sommelier") as websocket:
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"

        # 1. Отправляем текстовое сообщение без авторизации
        websocket.send_json({
            "type": "message",
            "content": "Посоветуй вино к стейку",
        })
        resp = websocket.receive_json()
        assert resp["type"] == "message"
        assert resp.get("registration_required") is True

        # 2. Проходим онбординг до шага 5 без авторизации
        for step in range(1, 5):
            websocket.send_json({"type": "answer", "step": step, "code": f"step_{step}", "answer": "val"})
            next_step = websocket.receive_json()
            assert next_step["type"] == "next_question"

        websocket.send_json({"type": "answer", "step": 5, "code": "aromas", "answer": "Спелые ягоды"})
        final_resp = websocket.receive_json()
        assert final_resp["type"] == "completed"
        assert final_resp.get("registration_required") is True
        assert final_resp.get("candidates") == []


def test_sommelier_websocket_authorized_flow():
    """Проверка диалога и завершения онбординга для авторизованного пользователя."""
    client = TestClient(app)
    token_pair = TokenService().create_token_pair(uuid.uuid4())
    token = token_pair.access_token

    # Подключаемся с токеном в query params
    with client.websocket_connect(f"/ws/sommelier?token={token}") as websocket:
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"

        # Свободный диалог разрешен для авторизованного пользователя
        websocket.send_json({
            "type": "message",
            "content": "Посоветуй легкое белое вино к морепродуктам",
            "stream": False,
        })
        resp = websocket.receive_json()
        assert resp["type"] == "message"
        assert resp["role"] == "assistant"
        assert resp.get("registration_required") is not True


def test_sommelier_websocket_auth_message():
    """Проверка динамической авторизации через сообщение type: auth."""
    client = TestClient(app)
    token_pair = TokenService().create_token_pair(uuid.uuid4())
    token = token_pair.access_token

    with client.websocket_connect("/ws/sommelier") as websocket:
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"

        # Отправляем сообщение авторизации
        websocket.send_json({
            "type": "auth",
            "token": token,
        })
        auth_resp = websocket.receive_json()
        assert auth_resp["type"] == "auth_success"
        assert "user_id" in auth_resp

        # Теперь текстовый чат не блокируется пейволлом
        websocket.send_json({
            "type": "message",
            "content": "Привет, сомелье!",
            "stream": False,
        })
        resp = websocket.receive_json()
        assert resp["type"] == "message"
        assert resp.get("registration_required") is not True



