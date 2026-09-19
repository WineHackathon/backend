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


def test_sommelier_websocket_connection():
    """Проверка подключения и интерактивного обмена через WebSocket (/ws/sommelier)."""
    client = TestClient(app)
    with client.websocket_connect("/ws/sommelier") as websocket:
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"
        assert "question" in welcome

        # Отправляем ответ на шаг 1
        websocket.send_json({"type": "answer", "step": 1, "code": "category", "answer": "Красное"})
        next_step = websocket.receive_json()
        assert next_step["type"] == "next_question"
        assert next_step["step"] == 2


def test_sommelier_websocket_copilot_chat():
    """Проверка свободного диалога с AI-копайлотом через WebSocket."""
    client = TestClient(app)
    with client.websocket_connect("/ws/sommelier") as websocket:
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"

        # Отправляем свободный запрос копайлоту
        websocket.send_json({
            "type": "message",
            "content": "Посоветуй легкое белое вино к морепродуктам",
            "stream": False,
        })
        resp = websocket.receive_json()
        assert resp["type"] == "message"
        assert resp["role"] == "assistant"
        assert len(resp["content"]) > 0
        assert "candidates" in resp


def test_sommelier_websocket_streaming():
    """Проверка потокового (streaming) диалога с AI-копайлотом через WebSocket."""
    client = TestClient(app)
    with client.websocket_connect("/ws/sommelier") as websocket:
        welcome = websocket.receive_json()
        assert welcome["type"] == "welcome"

        websocket.send_json({
            "type": "message",
            "content": "Что такое оранжевое вино?",
            "stream": True,
        })

        # Получаем стриминговые чанки
        chunks = []
        while True:
            msg = websocket.receive_json()
            if msg["type"] == "stream_chunk":
                chunks.append(msg["content"])
            elif msg["type"] == "stream_end":
                assert "candidates" in msg
                break

        assert len(chunks) > 0

