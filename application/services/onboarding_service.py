"""
Сервис онбординга и адаптивного диалога с цифровым сомелье.
Реализует сценарий «Оптимальный первый диалог» из 5 вопросов и адаптивных уточнений.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from application.dto.sommelier import (
    OnboardingQuestionDTO,
    OnboardingAnswerDTO,
    OnboardingStateDTO,
)
from application.services.catalog_service import CatalogService
from application.services.taste_profile_service import TasteProfileService


class SommelierOnboardingService:
    """Управление вопросами и адаптивными сценариями сомелье."""

    BASELINE_QUESTIONS = [
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
            question="Какие ароматы нравятся?",
            options=[
                "Спелые ягоды и вишня",
                "Цитрусы и зеленое яблоко",
                "Ваниль, дуб и пряности",
                "Полевые цветы и минералы",
                "Редкие и необычные вкусы (автохтоны, петнаты)",
            ],
        ),
    ]

    KNOWN_REGIONS = (
        "кубань",
        "долина дона",
        "дон",
        "крым",
        "севастополь",
        "дагестан",
        "волгоград",
        "геленджик",
        "новороссийск",
        "анапа",
        "тамань",
    )

    def get_question(self, step: int) -> OnboardingQuestionDTO:
        """Получение базового вопроса по номеру шага (1-5)."""
        if 1 <= step <= len(self.BASELINE_QUESTIONS):
            return self.BASELINE_QUESTIONS[step - 1]
        return self.BASELINE_QUESTIONS[-1]

    def get_adaptive_question(self, step: int, answers: dict[str, str]) -> OnboardingQuestionDTO:
        """
        Адаптивная генерация вопроса в зависимости от предыдущих ответов:
        - если выбрано красное -> уточнить oak и плотность;
        - если белое -> уточнить кислотность, фруктовость и минеральность;
        - если любит необычное -> спросить про автохтонные сорта и регион (если регион еще не выбран);
        - если уже выбран конкретный регион -> не переспрашивать его повторно.
        """
        cat = answers.get("category", "").lower()
        likes_unusual = any(
            keyword in str(v).lower()
            for v in answers.values()
            for keyword in ("необычн", "автохтон", "петнат", "оранж")
        )
        has_region = any(
            reg in str(v).lower()
            for v in answers.values()
            for reg in self.KNOWN_REGIONS
        ) or bool(answers.get("region"))

        # Адаптация шага 3: плотность и выдержка в дубе
        if step == 3 and "красн" in cat:
            return OnboardingQuestionDTO(
                step=3,
                code="body_oak",
                question="Для красного вина: вам ближе бархатистое вино с выдержкой в дубе или более ягодное и легкое?",
                options=["Мощное, с благородным дубом и танинами", "Легкое, ягодное и питкое"],
                adaptive=True,
            )

        # Адаптация шага 4: кислотность и минеральность
        if step == 4 and "бел" in cat:
            return OnboardingQuestionDTO(
                step=4,
                code="acidity_minerals",
                question="Для белого вина: важна ли для вас хрустящая кислотность и минеральность (морской бриз, кремень)?",
                options=["Яркая кислотность и минеральность", "Мягкая фруктовость и округлость"],
                adaptive=True,
            )

        # Адаптация шага 5: необычное, автохтоны и регионы
        if step == 5 and likes_unusual:
            if has_region:
                # Регион уже выбран ранее - спрашиваем только про автохтоны
                return OnboardingQuestionDTO(
                    step=5,
                    code="autochthons",
                    question="Хотите попробовать уникальные российские автохтонные сорта (Красностоп, Кокур, Цимлянский черный)?",
                    options=["Да, хочу редкие автохтоны!", "Предпочитаю классические международные сорта"],
                    adaptive=True,
                )
            else:
                # Регион еще не выбран - спрашиваем про автохтоны и регионы
                return OnboardingQuestionDTO(
                    step=5,
                    code="autochthons_region",
                    question="Хотите попробовать уникальные российские автохтоны и терруары (Красностоп, Кокур, Долина Дона, Крым)?",
                    options=["Да, хочу редкие автохтоны и терруары!", "Предпочитаю классические сорта (Кубань, Тамань)"],
                    adaptive=True,
                )

        return self.get_question(step)

    async def process_answer(
        self,
        dto: OnboardingAnswerDTO,
        user_id: uuid.UUID | None,
        session: AsyncSession,
    ) -> OnboardingStateDTO:
        """
        Оркестрация обработки шага онбординга:
        - Шаги 1-4: адаптивный выбор следующего вопроса.
        - Шаг 5 (аноним): пейволл / требование регистрации (registration_required: true).
        - Шаг 5 (авторизован): подбор вин по вкусовой матрице и фоновое обновление профиля.
        """
        step, code, answer_text, current_answers = dto.get_parsed_data()
        current_answers[code] = answer_text

        # Шаги 1-4: отдаем следующий адаптивный вопрос
        if step < 5:
            next_step = step + 1
            next_q = self.get_adaptive_question(step=next_step, answers=current_answers)
            return OnboardingStateDTO(
                current_step=step,
                answers=current_answers,
                next_question=next_q,
                completed=False,
                candidates=[],
                registration_required=False,
            )

        # Шаг 5: опросник завершен
        if not user_id:
            return OnboardingStateDTO(
                current_step=5,
                answers=current_answers,
                next_question=None,
                completed=True,
                candidates=[],
                registration_required=True,
            )

        # Авторизованный пользователь: поиск кандидатов по вкусовой матрице
        catalog_service = CatalogService(session)
        candidates = await catalog_service.search_by_taste_matrix(
            category=current_answers.get("category"),
            target_sweetness=1.2 if "сух" in str(current_answers.get("sweetness", "")).lower() else 3.0,
            target_body=4.0 if "плотн" in str(current_answers.get("body", "")).lower() else 2.5,
            target_acidity=4.0 if "свежест" in str(current_answers.get("acidity", "")).lower() else 2.5,
            limit=5,
        )

        # Фоновое обновление вкусового профиля пользователя
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

