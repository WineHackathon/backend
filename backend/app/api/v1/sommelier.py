import logging
import uuid
import httpx
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.sommelier import (
    OnboardingQuestionDTO,
    OnboardingAnswerDTO,
    OnboardingStateDTO,
    SommelierChatRequestDTO,
    SommelierChatResponseDTO,
)
from application.services.catalog_service import CatalogService
from application.services.taste_profile_service import TasteProfileService
from application.services.onboarding_service import SommelierOnboardingService
from backend.app.config import settings
from backend.app.dependencies import get_optional_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sommelier", tags=["Цифровой сомелье"])

onboarding_service = SommelierOnboardingService()
ONBOARDING_QUESTIONS = SommelierOnboardingService.BASELINE_QUESTIONS


@router.get("/onboarding/questions", response_model=list[OnboardingQuestionDTO], summary="Получить 5 базовых вопросов онбординга")
async def get_onboarding_questions():
    """Получение стартовых 5 вопросов для диалога с сомелье."""
    return ONBOARDING_QUESTIONS


@router.post("/onboarding/answer", response_model=OnboardingStateDTO, summary="Отправить ответ на вопрос сомелье и получить следующий шаг")
async def submit_onboarding_answer(
    answer: OnboardingAnswerDTO,
    answers_history: dict[str, str] | None = None,
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Обработка шага онбординга:
    - Если пользователь анонимный и дошел до конца: возвращается registration_required: true и тизер.
    - Если пользователь авторизован: возвращаются подобранные винные карточки и запускается фоновое обновление профиля.
    """
    current_answers = answers_history or {}
    current_answers[answer.code] = answer.answer
    step = answer.step

    # Проверка, есть ли следующий вопрос
    if step < 5:
        next_step = step + 1
        next_q = onboarding_service.get_adaptive_question(step=next_step, answers=current_answers)

        return OnboardingStateDTO(
            current_step=step,
            answers=current_answers,
            next_question=next_q,
            completed=False,
            candidates=[],
            registration_required=False,
        )

    # Завершены все 5 вопросов
    # Если пользователь не авторизован -> отдаем пейволл (registration_required)
    if not user_id:
        return OnboardingStateDTO(
            current_step=5,
            answers=current_answers,
            next_question=None,
            completed=True,
            candidates=[],
            registration_required=True,  # Запрос регистрации для получения винных карточек
        )

    # Для авторизованного пользователя подбираем кандидатов по вкусовой матрице
    catalog_service = CatalogService(session)
    candidates = await catalog_service.search_by_taste_matrix(
        category=current_answers.get("category"),
        target_sweetness=1.2 if "сух" in current_answers.get("sweetness", "").lower() else 3.0,
        target_body=4.0 if "плотн" in current_answers.get("body", "").lower() else 2.5,
        target_acidity=4.0 if "свежест" in current_answers.get("acidity", "").lower() else 2.5,
        limit=5,
    )

    # Фоновое обновление профиля пользователя
    taste_service = TasteProfileService(session)
    session_id = str(uuid.uuid4())
    recommended_slugs = [c.slug for c in candidates]
    await taste_service.record_preferences_and_update_profile(
        user_id=user_id,
        session_id=session_id,
        raw_answers=current_answers,
        recommended_slugs=recommended_slugs,
    )

    return OnboardingStateDTO(
        current_step=5,
        answers=current_answers,
        next_question=None,
        completed=True,
        candidates=candidates,
        registration_required=False,
    )


@router.post("/chat", response_model=SommelierChatResponseDTO, summary="Диалог с AI-сомелье (чат)")
async def chat_with_sommelier(
    request: SommelierChatRequestDTO,
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
):
    """
    HTTP проксирование диалога в специализированный сервис sommelier.
    """
    # Проверка авторизации: неавторизованным возвращаем требование регистрации
    if not user_id:
        return SommelierChatResponseDTO(
            reply="Чтобы получить персонализированную рекомендацию вин от цифрового сомелье, пожалуйста, зарегистрируйтесь или войдите в аккаунт.",
            recommended_slugs=[],
            food_pairings=[],
            registration_required=True,
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.sommelier_service_url}/api/v1/sommelier/chat",
                json=request.model_dump(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Ошибка обращения к сервису сомелье: {exc}. Использование fallback ответа.")

    # Интеллектуальный fallback
    return SommelierChatResponseDTO(
        reply="Здравствуйте! Я ваш цифровой сомелье. Выберите категорию или пройдите короткий опрос из 5 вопросов для точного подбора!",
        recommended_slugs=[],
        food_pairings=[],
    )
