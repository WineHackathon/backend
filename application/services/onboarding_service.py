"""
Сервис онбординга и адаптивного диалога с цифровым сомелье.
Реализует сценарий «Оптимальный первый диалог» из 5 вопросов и адаптивных уточнений.
"""
from application.dto.sommelier import OnboardingQuestionDTO


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
