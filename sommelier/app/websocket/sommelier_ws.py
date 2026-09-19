"""
WebSocket обработчик (/ws/sommelier) для интерактивного стриминга диалога с сомелье в реальном времени.
"""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from sommelier.app.services.onboarding_service import SommelierOnboardingService
from sommelier.app.services.recommendation_engine import SommelierRecommendationEngine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sommelier WebSocket"])


@router.websocket("/ws/sommelier")
async def sommelier_websocket_endpoint(websocket: WebSocket):
    """
    Интерактивный WebSocket протокол диалога:
    1. При подключении отправляет приветствие и 1-й вопрос онбординга.
    2. Принимает ответы от клиента: {"type": "answer", "step": 1, "code": "category", "answer": "Красное"}.
    3. Отправляет адаптивный следующий вопрос.
    4. На 5 шаге: выдает подобранные карточки вин или предложение зарегистрироваться для гостей.
    """
    await websocket.accept()
    onboarding_service = SommelierOnboardingService()
    recommendation_engine = SommelierRecommendationEngine()

    answers: dict[str, str] = {}
    current_step = 1

    try:
        # Отправляем приветствие и вопрос №1
        first_q = onboarding_service.get_question(step=1)
        await websocket.send_json({
            "type": "welcome",
            "message": "Приветствую! Я ваш цифровой AI-сомелье. Давайте подберем идеальное вино по вашему вкусу!",
            "question": first_q.model_dump(),
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "answer":
                step = data.get("step", current_step)
                code = data.get("code")
                answer_val = data.get("answer")

                if code and answer_val:
                    answers[code] = answer_val

                if step < 5:
                    current_step = step + 1
                    # Адаптивный выбор следующего вопроса
                    next_q = onboarding_service.get_adaptive_question(step=current_step, answers=answers)
                    await websocket.send_json({
                        "type": "next_question",
                        "step": current_step,
                        "question": next_q.model_dump(),
                    })
                else:
                    # Опрос завершен: генерируем результат
                    mock_candidates = [
                        {
                            "slug": "fanagoria-cru-2020",
                            "name": "Фанагория Крю Лермонт Каберне Совиньон",
                            "category": answers.get("category", "Красное"),
                            "sweetness": 1.2,
                            "body": 4.5,
                            "acidity": 3.0,
                            "oak": 4.0,
                            "aroma_tags": ["вишня", "дуб", "черная смородина"],
                        },
                        {
                            "slug": "usadba-divnomorskoe-2021",
                            "name": "Усадьба Дивноморское Восточный Склон",
                            "category": answers.get("category", "Белое"),
                            "sweetness": 1.1,
                            "body": 2.5,
                            "acidity": 4.2,
                            "oak": 1.5,
                            "aroma_tags": ["цитрус", "белые цветы", "минералы"],
                        },
                    ]

                    ranked = recommendation_engine.rank_candidates(
                        candidates=mock_candidates,
                        target_sweetness=1.2 if "сух" in answers.get("sweetness", "").lower() else 3.0,
                        target_body=4.5 if "плотн" in answers.get("body", "").lower() or "дуб" in answers.get("body_oak", "").lower() else 2.5,
                    )

                    await websocket.send_json({
                        "type": "completed",
                        "message": "Превосходно! Ваш вкусовой профиль сформирован. Вот лучшие кандидаты:",
                        "candidates": ranked,
                        "registration_prompt": "Зарегистрируйтесь, чтобы сохранить эти вина в личный погреб и отслеживать историю дегустаций!",
                    })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Клиент отключился от WebSocket сомелье.")
    except Exception as e:
        logger.error(f"Ошибка в WebSocket сессии: {e}", exc_info=True)
        try:
            await websocket.close()
        except Exception:
            pass
