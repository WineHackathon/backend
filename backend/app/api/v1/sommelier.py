"""
Эндпоинты цифрового сомелье и онбординга (/api/v1/sommelier).
Тонкие контроллеры: бизнес-логика шагов делегирована в SommelierOnboardingService.
"""
import logging
import uuid
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from application.adapters.database.db_session import get_session
from application.dto.sommelier import (
    OnboardingQuestionDTO,
    OnboardingAnswerDTO,
    OnboardingStateDTO,
    SommelierChatRequestDTO,
    SommelierChatResponseDTO,
)
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
    dto: OnboardingAnswerDTO,
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
    session: AsyncSession = Depends(get_session),
):
    """
    Обработка шага онбординга:
    Делегирует оркестрацию в SommelierOnboardingService.process_answer.
    """
    return await onboarding_service.process_answer(
        dto=dto,
        user_id=user_id,
        session=session,
    )


@router.post("/chat", response_model=SommelierChatResponseDTO, summary="Диалог с AI-сомелье (чат)")
async def chat_with_sommelier(
    request: SommelierChatRequestDTO,
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
):
    """
    HTTP проксирование диалога в специализированный сервис сомелье.
    Неавторизованным пользователям возвращает требование регистрации.
    """
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
        logger.warning("Ошибка обращения к сервису сомелье: %s. Использование fallback ответа.", exc)

    # Интеллектуальный fallback при недоступности внешнего сервиса
    return SommelierChatResponseDTO(
        reply="Здравствуйте! Я ваш цифровой сомелье. Выберите категорию или пройдите короткий опрос из 5 вопросов для точного подбора!",
        recommended_slugs=[],
        food_pairings=[],
    )
