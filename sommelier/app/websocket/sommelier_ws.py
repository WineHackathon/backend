"""
WebSocket обработчик (/ws/sommelier) для интерактивного диалога с AI-Сомелье (Copilot) в реальном времени.
Поддерживает:
1. Свободный диалог с AI-копайлотом через OpenRouter (streaming и non-streaming).
2. Поиск и подбор похожих вин на основе запроса или выбранного вина (context_wine_slug).
3. 5-вопросный интерактивный онбординг.
"""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from application.adapters.database.db_session import create_session
from application.adapters.database.repositories.user_repo import UserRepository
from application.services.catalog_service import CatalogService
from application.services.token_service import TokenService
from application.services.taste_profile_service import TasteProfileService
from sommelier.app.services.onboarding_service import SommelierOnboardingService
from sommelier.app.services.recommendation_engine import SommelierRecommendationEngine
from sommelier.app.services.llm_client import SommelierLLMClient
from sommelier.app.services.rag_service import SommelierRAGService
from sommelier.app.services.intent_extractor import intent_extractor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sommelier WebSocket"])


@asynccontextmanager
async def _get_catalog_service():
    """Безопасное получение сервиса каталога с сессией БД в контекстном менеджере."""
    async with create_session() as session:
        yield CatalogService(session)


@router.websocket("/ws/sommelier")
async def sommelier_websocket_endpoint(websocket: WebSocket):
    """
    Интерактивный WebSocket протокол AI-Сомелье (Copilot):
    - type: "message" / "chat": свободный диалог с AI-копайлотом через OpenRouter + подбор вин.
    - type: "answer": 5-шаговый адаптивный опрос предпочтений.
    - type: "ping": проверка соединения.
    """
    await websocket.accept()
    onboarding_service = SommelierOnboardingService()
    recommendation_engine = SommelierRecommendationEngine()
    llm_client = SommelierLLMClient()
    rag_service = SommelierRAGService()
    token_service = TokenService()

    # Аутентификация через query parameter ?token=...
    user_id: uuid.UUID | None = None
    user_name: str = "пользователь"
    user_taste_profile: dict = {}
    has_taste_profile: bool = False

    query_token = websocket.query_params.get("token")
    if query_token:
        try:
            payload = token_service.decode_access_token(query_token)
            user_id = payload.sub
            async with create_session() as session:
                user_repo = UserRepository(session)
                user = await user_repo.get_by_id(user_id)
                if user:
                    user_name = user.first_name or "пользователь"
                    user_taste_profile = user.taste_profile or {}
                    if user_taste_profile.get("preferred_categories") or user_taste_profile.get("sweetness_pref") is not None:
                        has_taste_profile = True
        except Exception as e:
            logger.warning(f"Недействительный токен в query params WebSocket: {e}")

    answers: dict[str, str] = {}
    current_step = 1
    chat_history: list[dict[str, str]] = []
    onboarding_completed = False

    async def _finish_and_send_recommendations(target_user_id: uuid.UUID) -> None:
        """Подбор вин по вкусовой матрице, сохранение профиля в БД и отправка события completed."""
        final_candidates = []
        async with _get_catalog_service() as catalog_service:
            if catalog_service:
                try:
                    final_candidates = await catalog_service.search_by_taste_matrix(
                        category=answers.get("category"),
                        target_sweetness=1.2 if "сух" in answers.get("sweetness", "").lower() else 3.0,
                        target_body=4.5 if "плотн" in answers.get("body", "").lower() or "дуб" in answers.get("body_oak", "").lower() else 2.5,
                        target_acidity=4.0 if "свежест" in answers.get("acidity", "").lower() else 2.5,
                        limit=4,
                    )
                except Exception as e:
                    logger.warning(f"Ошибка подбора вин по вкусовой матрице в онбординге: {e}")

        if not final_candidates:
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
            final_candidates = ranked

        candidates_data = [
            c.model_dump(mode="json") if hasattr(c, "model_dump") else c
            for c in final_candidates
        ]

        # Фоновое сохранение вкусового профиля и сессии предпочтений пользователя в БД
        try:
            async with create_session() as session:
                taste_service = TasteProfileService(session)
                session_id = str(uuid.uuid4())
                recommended_slugs = [
                    c.slug if hasattr(c, "slug") else c.get("slug")
                    for c in final_candidates
                    if (hasattr(c, "slug") and c.slug) or (isinstance(c, dict) and c.get("slug"))
                ]
                await taste_service.record_preferences_and_update_profile(
                    user_id=target_user_id,
                    session_id=session_id,
                    raw_answers=answers,
                    recommended_slugs=recommended_slugs,
                )
        except Exception as exc:
            logger.warning("Не удалось обновить вкусовой профиль пользователя %s: %s", target_user_id, exc)

        await websocket.send_json({
            "type": "completed",
            "message": "Превосходно! Ваш вкусовой профиль сформирован. Вот лучшие кандидаты по вашему вкусу:",
            "candidates": candidates_data,
            "registration_required": False,
        })

    try:
        # Отправляем приветствие с учетом сохраненного вкусового профиля
        if has_taste_profile:
            cat_info = ", ".join(user_taste_profile.get("preferred_categories", [])) or "разные вина"
            await websocket.send_json({
                "type": "welcome",
                "message": (
                    f"Приветствую, {user_name}! Я помню ваши вкусовые предпочтения ({cat_info}). "
                    "Вы можете задать мне любой вопрос о винах и гастропарах (например, «подбери вино к стейку» или «к рыбе»), "
                    "попросить найти аналог вина или пройти опрос заново."
                ),
                "has_taste_profile": True,
                "taste_profile": user_taste_profile,
                "question": None,
            })
        else:
            first_q = onboarding_service.get_question(step=1)
            await websocket.send_json({
                "type": "welcome",
                "message": (
                    "Приветствую! Я ваш цифровой AI-сомелье и персональный винный копайлот. "
                    "Вы можете задавать мне любые вопросы о вине, регионах и гастропарах, "
                    "попросить найти похожие вина или пройти быстрый подбор из 5 вопросов!"
                ),
                "has_taste_profile": False,
                "question": first_q.model_dump(),
            })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            # -----------------------------------------------------------------
            # 0. Авторизация в процессе соединения (type: "auth")
            # -----------------------------------------------------------------
            if msg_type == "auth":
                auth_token = data.get("token")
                if auth_token:
                    try:
                        payload = token_service.decode_access_token(auth_token)
                        user_id = payload.sub
                        async with create_session() as session:
                            user_repo = UserRepository(session)
                            u = await user_repo.get_by_id(user_id)
                            if u:
                                user_name = u.first_name or "пользователь"
                                user_taste_profile = u.taste_profile or {}
                                if user_taste_profile.get("preferred_categories") or user_taste_profile.get("sweetness_pref") is not None:
                                    has_taste_profile = True

                        await websocket.send_json({
                            "type": "auth_success",
                            "user_id": str(user_id),
                            "message": "Успешная авторизация в сессии сомелье.",
                            "has_taste_profile": has_taste_profile,
                            "taste_profile": user_taste_profile,
                        })
                        # Если пользователь уже прошел 5 вопросов до авторизации — сразу отдаем рекомендации
                        if onboarding_completed:
                            await _finish_and_send_recommendations(user_id)
                    except Exception as e:
                        logger.warning(f"Ошибка WebSocket auth: {e}")
                        await websocket.send_json({
                            "type": "auth_error",
                            "message": "Недействительный или истекший токен авторизации.",
                        })
                else:
                    await websocket.send_json({
                        "type": "auth_error",
                        "message": "Токен не предоставлен.",
                    })
                continue

            # -----------------------------------------------------------------
            # 0.1 Явный перезапуск онбординга пользователем (type: "start_onboarding")
            # -----------------------------------------------------------------
            if msg_type == "start_onboarding":
                answers.clear()
                current_step = 1
                onboarding_completed = False
                first_q = onboarding_service.get_question(step=1)
                await websocket.send_json({
                    "type": "next_question",
                    "step": 1,
                    "question": first_q.model_dump(),
                })
                continue

            # -----------------------------------------------------------------
            # 1. Свободный диалог с AI-Копайлотом (type: "message" или "chat")
            # -----------------------------------------------------------------
            if msg_type in ("message", "chat"):
                user_text = (data.get("content") or data.get("message") or data.get("text") or "").strip()
                if not user_text:
                    continue

                # Пейволл для неавторизованных пользователей
                if not user_id:
                    await websocket.send_json({
                        "type": "message",
                        "role": "assistant",
                        "content": "Чтобы получить персональную рекомендацию от AI-сомелье, пожалуйста, зарегистрируйтесь или войдите в аккаунт.",
                        "candidates": [],
                        "registration_required": True,
                    })
                    continue

                stream_enabled = bool(data.get("stream", False))
                context_wine_slug = data.get("context_wine_slug")

                chat_history.append({"role": "user", "content": user_text})

                # Поиск кандидатов в каталоге
                candidates: list[Any] = []
                context_wine_dict = None
                async with _get_catalog_service() as catalog_service:
                    if catalog_service:
                        try:
                            # 1. Если задан конкретный контекст вина
                            if context_wine_slug:
                                try:
                                    detail = await catalog_service.get_by_slug(context_wine_slug)
                                    context_wine_dict = detail.model_dump()
                                    # Ищем похожие вина по вкусовой матрице
                                    candidates = await catalog_service.find_similar_wines(context_wine_slug, limit=3)
                                except Exception:
                                    pass

                            # 2. Если пользователь просит найти похожее вино
                            elif any(k in user_text.lower() for k in ("похож", "аналог", "замен")):
                                clean_q = user_text.lower().replace("найди", "").replace("похожее", "").replace("на", "").replace("вино", "").strip()
                                if clean_q:
                                    found = await catalog_service.list_wines(query=clean_q, limit=1)
                                    if found.items:
                                        base_slug = found.items[0].slug
                                        candidates = await catalog_service.find_similar_wines(base_slug, limit=3)

                            # 3. Интеллектуальный многокритериальный поиск по намерениям (Intent Extractor)
                            if not candidates:
                                intent = await intent_extractor.extract_intent(user_text, llm_client)
                                # Если в запросе не указана категория или сладость, учитываем вкусовой профиль пользователя
                                if user_taste_profile:
                                    if not intent.category and user_taste_profile.get("preferred_categories"):
                                        intent.category = user_taste_profile["preferred_categories"][0]
                                    if not intent.sugar_type and user_taste_profile.get("sweetness_pref") is not None:
                                        if user_taste_profile["sweetness_pref"] <= 1.8:
                                            intent.sugar_type = "Сухое"
                                candidates = await catalog_service.recommend_wines_by_intent(intent, limit=3)

                        except Exception as exc:
                            logger.warning(f"Ошибка поиска вин в каталоге для копайлота: {exc}")

                # Формируем системный контекст для LLM (RAG)
                system_prompt = rag_service.build_system_prompt(context_wine=context_wine_dict)
                if user_taste_profile:
                    pref_parts = []
                    if user_taste_profile.get("preferred_categories"):
                        pref_parts.append(f"Любимые категории: {', '.join(user_taste_profile['preferred_categories'])}")
                    if user_taste_profile.get("sweetness_pref") is not None:
                        pref_parts.append(f"Сладость: {user_taste_profile['sweetness_pref']}/5")
                    if user_taste_profile.get("body_pref") is not None:
                        pref_parts.append(f"Тело/плотность: {user_taste_profile['body_pref']}/5")
                    if user_taste_profile.get("favorite_aromas"):
                        pref_parts.append(f"Любимые ароматы: {', '.join(user_taste_profile['favorite_aromas'])}")
                    if pref_parts:
                        system_prompt += f"\n\nПостоянный вкусовой профиль пользователя: {'; '.join(pref_parts)}. Учитывайте его персональные вкусы при рекомендации."

                if candidates:
                    candidates_summary = "\n".join([
                        f"- {c.name} (Категория: {c.category}, Сахар: {c.sugar_type or 'Сухое'}, Регион: {c.region or 'Россия'}, "
                        f"Оценка Роскачества: {c.roskachestvo_score or 'Н/Д'}/100, Тело/плотность: {c.body or 'умеренное'}/5, "
                        f"Кислотность: {c.acidity or 'сбалансированная'}/5, Дуб: {c.oak or 'нет'}/5, Цена: ~{c.price_rub or 'Н/Д'} руб.)"
                        for c in candidates
                    ])
                    system_prompt += (
                        f"\n\nПодобранные актуальные российские вина из каталога для рекомендации:\n{candidates_summary}\n"
                        "ОБЯЗАТЕЛЬНО упомяните эти вина в ответе. Ответьте лаконично и емко (2 коротких абзаца, до 100-120 слов). "
                        "Поясните, почему эти образцы гармонируют с запросом (танины, плотность, кислотность, блюдо)."
                    )

                candidates_data = [
                    c.model_dump(mode="json") if hasattr(c, "model_dump") else c
                    for c in candidates
                ]

                # Фаза 1: Мгновенная отправка карточек вин клиенту (15-20 мс)
                if candidates_data:
                    await websocket.send_json({
                        "type": "candidates_ready",
                        "candidates": candidates_data,
                    })

                # Фаза 2: Генерация ответа (потоковая или единая)
                if stream_enabled:
                    full_reply = []
                    async for chunk in llm_client.stream_response(system_prompt, chat_history):
                        full_reply.append(chunk)
                        await websocket.send_json({
                            "type": "stream_chunk",
                            "content": chunk,
                        })
                    complete_text = "".join(full_reply)
                    chat_history.append({"role": "assistant", "content": complete_text})
                    await websocket.send_json({
                        "type": "stream_end",
                        "candidates": candidates_data,
                    })
                else:
                    reply = await llm_client.generate_response(system_prompt, chat_history)
                    if not reply or not str(reply).strip():
                        reply = llm_client._build_smart_fallback_reply(system_prompt, chat_history)
                    chat_history.append({"role": "assistant", "content": reply})
                    await websocket.send_json({
                        "type": "message",
                        "role": "assistant",
                        "content": reply,
                        "candidates": candidates_data,
                    })

            # -----------------------------------------------------------------
            # 2. Интерактивный 5-вопросный онбординг (type: "answer")
            # -----------------------------------------------------------------
            elif msg_type == "answer":
                step = int(data.get("step", current_step))
                code = data.get("code")
                answer_val = data.get("answer") or data.get("text") or data.get("value")

                if not code:
                    step_codes = {1: "category", 2: "sweetness", 3: "body", 4: "acidity", 5: "aromas"}
                    code = step_codes.get(step, f"step_{step}")

                if code and answer_val:
                    answers[code] = str(answer_val)

                if step < 5:
                    current_step = step + 1
                    next_q = onboarding_service.get_adaptive_question(step=current_step, answers=answers)
                    await websocket.send_json({
                        "type": "next_question",
                        "step": current_step,
                        "question": next_q.model_dump(),
                    })
                else:
                    # Завершены 5 вопросов онбординга
                    onboarding_completed = True

                    # Пейволл для неавторизованных гостей
                    if not user_id:
                        await websocket.send_json({
                            "type": "completed",
                            "message": "Превосходно! Ваш вкусовой профиль сформирован. Зарегистрируйтесь, чтобы получить персональные винные рекомендации.",
                            "candidates": [],
                            "registration_required": True,
                        })
                        continue

                    # Для авторизованного пользователя: сразу выдаем подбор и сохраняем профиль
                    await _finish_and_send_recommendations(user_id)

            # -----------------------------------------------------------------
            # 3. Healthcheck ping-pong
            # -----------------------------------------------------------------
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

