"""
Эндпоинты взаимодействия с цифровым сомелье (/api/v1/sommelier).
Включает 5-вопросный онбординг с пейволлом для гостей и диалоговый чат.
"""
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
from backend.app.config import settings
from backend.app.dependencies import get_optional_user_id

router = APIRouter(prefix="/api/v1/sommelier", tags=["Digital Sommelier"])


# 5 базовых вопросов оптимального первого диалога
ONBOARDING_QUESTIONS = [
    OnboardingQuestionDTO(
        step=1,
        code="category",
        question="Белое, красное, розовое или игристое?",
        options=["Белое", "Красное", "Розовое", "Игристое"],
    ),
    OnboardingQuestionDTO(
        step=2,
        code="sweetness",
        question="Сухое или с остаточной сладостью?",
        options=["Сухое", "С остаточной сладостью"],
    ),
    OnboardingQuestionDTO(
        step=3,
        code="body",
        question="Лёгкое, среднее или плотное?",
        options=["Лёгкое", "Среднее", "Плотное"],
    ),
    OnboardingQuestionDTO(
        step=4,
        code="acidity",
        question="Больше свежести или мягкости?",
        options=["Больше свежести", "Больше мягкости"],
    ),
    OnboardingQuestionDTO(
        step=5,
        code="aromas",
        question="Какие ароматы вам нравятся больше всего?",
        options=["Спелые ягоды и вишня", "Цитрусы и зеленое яблоко", "Ваниль, дуб и шоколад", "Полевые цветы и минералы"],
    ),
]


@router.get("/onboarding/questions", response_model=list[OnboardingQuestionDTO], summary="Get 5 baseline onboarding questions")
async def get_onboarding_questions():
    """Получение стартовых 5 вопросов для диалога с сомелье."""
    return ONBOARDING_QUESTIONS


@router.post("/onboarding/answer", response_model=OnboardingStateDTO, summary="Submit onboarding answer and get next question or candidates")
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
        next_q = ONBOARDING_QUESTIONS[step]
        # Адаптивная корректировка вопроса в зависимости от категории
        cat = current_answers.get("category", "").lower()
        if step == 2 and "красн" in cat:
            next_q = OnboardingQuestionDTO(
                step=3,
                code="body",
                question="Для красного: предпочитаете плотное танинное или мягкое бархатистое?",
                options=["Плотное и танинное", "Мягкое и бархатистое"],
                adaptive=True,
            )
        elif step == 3 and "бел" in cat:
            next_q = OnboardingQuestionDTO(
                step=4,
                code="acidity",
                question="Для белого: важнее яркая кислотность и минеральность или фруктовость?",
                options=["Яркая кислотность и минеральность", "Фруктовая мягкость"],
                adaptive=True,
            )

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
    from application.services.catalog_service import CatalogService
    from application.services.taste_profile_service import TasteProfileService

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


@router.post("/chat", response_model=SommelierChatResponseDTO, summary="Chat with AI sommelier")
async def chat_with_sommelier(
    request: SommelierChatRequestDTO,
    user_id: uuid.UUID | None = Depends(get_optional_user_id),
):
    """
    HTTP проксирование диалога в специализированный сервис sommelier.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.sommelier_service_url}/api/v1/sommelier/chat",
                json=request.model_dump(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass

    # Интеллектуальный fallback
    return SommelierChatResponseDTO(
        reply="Здравствуйте! Я ваш цифровой сомелье. Выберите категорию или пройдите короткий опрос из 5 вопросов для точного подбора!",
        recommended_slugs=[],
        food_pairings=[],
    )
