"""
DTO схемы для диалога с цифровым сомелье и 5-вопросного онбординга.
"""
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from application.dto.wine import WineDTO


class OnboardingQuestionDTO(BaseModel):
    """Вопрос из 5-шагового онбординга сомелье."""
    step: int
    question: str
    code: str
    options: list[str]
    adaptive: bool = False

    model_config = ConfigDict(from_attributes=True)


class OnboardingAnswerDTO(BaseModel):
    """
    Ответ пользователя на вопрос онбординга.
    Поддерживает как плоский формат: {"step": 1, "code": "category", "answer": "Белое", "answers_history": {...}},
    так и вложенный формат: {"answer": {"step": 1, "code": "category", "answer": "Белое"}, "answers_history": {...}}.
    """
    step: int | None = Field(default=None, description="Номер шага (1-5)")
    code: str | None = Field(default=None, description="Код вопроса (category, sweetness, body, acidity, aromas)")
    answer: str | dict[str, Any] = Field(description="Текст ответа или вложенный объект ответа")
    answers_history: dict[str, str] = Field(default_factory=dict, description="Ранее накопленные ответы онбординга")

    def get_parsed_data(self) -> tuple[int, str, str, dict[str, str]]:
        if isinstance(self.answer, dict):
            step = int(self.answer.get("step", self.step or 1))
            code = str(self.answer.get("code", self.code or "category"))
            ans = str(self.answer.get("answer", ""))
        else:
            step = int(self.step or 1)
            code = str(self.code or "category")
            ans = str(self.answer)
        return step, code, ans, dict(self.answers_history or {})


class OnboardingStateDTO(BaseModel):
    """Текущее состояние процесса онбординга."""
    current_step: int
    total_steps: int = 5
    answers: dict[str, str] = Field(default_factory=dict)
    next_question: OnboardingQuestionDTO | None = None
    completed: bool = False
    candidates: list[WineDTO] = Field(default_factory=list)
    registration_required: bool = False

    model_config = ConfigDict(from_attributes=True)


class SommelierChatMessageDTO(BaseModel):
    """Сообщение в диалоге с сомелье."""
    role: str = Field(description="Роль: user, assistant, system")
    content: str = Field(description="Текст сообщения")

    model_config = ConfigDict(from_attributes=True)


class SommelierChatRequestDTO(BaseModel):
    """Запрос диалога к AI-сомелье."""
    messages: list[SommelierChatMessageDTO]
    context_wine_slug: str | None = None


class SommelierChatResponseDTO(BaseModel):
    """Ответ AI-сомелье с рекомендованными винами."""
    reply: str
    recommended_slugs: list[str] = Field(default_factory=list)
    food_pairings: list[str] = Field(default_factory=list)
    registration_required: bool = False

    model_config = ConfigDict(from_attributes=True)
