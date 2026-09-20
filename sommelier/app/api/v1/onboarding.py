"""
HTTP эндпоинты онбординга сомелье (/api/v1/sommelier/onboarding).
"""
from fastapi import APIRouter
from application.dto.sommelier import OnboardingQuestionDTO
from sommelier.app.services.onboarding_service import SommelierOnboardingService

router = APIRouter(prefix="/api/v1/sommelier/onboarding", tags=["Онбординг сомелье"])


@router.get("/questions", response_model=list[OnboardingQuestionDTO], summary="Базовые вопросы онбординга")
async def get_questions():
    """Получение базовых вопросов онбординга."""
    service = SommelierOnboardingService()
    return service.BASELINE_QUESTIONS
