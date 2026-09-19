"""
DTO схемы для диалога с цифровым сомелье и 5-вопросного онбординга.
"""
from pydantic import BaseModel, Field
from application.dto.wine import WineDTO


class OnboardingQuestionDTO(BaseModel):
    """Вопрос из 5-шагового онбординга сомелье."""
    step: int
    question: str
    code: str
    options: list[str]
    adaptive: bool = False


class OnboardingAnswerDTO(BaseModel):
    """Ответ пользователя на вопрос онбординга."""
    step: int
    code: str
    answer: str


class OnboardingStateDTO(BaseModel):
    """Текущее состояние процесса онбординга."""
    current_step: int
    total_steps: int = 5
    answers: dict[str, str] = Field(default_factory=dict)
    next_question: OnboardingQuestionDTO | None = None
    completed: bool = False
    candidates: list[WineDTO] = Field(default_factory=list)
    registration_required: bool = False


class SommelierChatMessageDTO(BaseModel):
    """Сообщение в диалоге с сомелье."""
    role: str = Field(description="Роль: user, assistant, system")
    content: str = Field(description="Текст сообщения")


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
