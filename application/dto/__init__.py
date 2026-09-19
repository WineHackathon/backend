"""
Экспорт всех DTO схем слоя application.
"""
from .wine import (
    WineDTO,
    WineDetailDTO,
    TasteMatrixDTO,
    FoodPairingDTO,
    WineFilterDTO,
    TasteMatrixSearchDTO,
    PaginatedWinesDTO,
)
from .user import (
    UserDTO,
    TasteProfileDTO,
    UserPreferenceHistoryDTO,
    UserCreateDTO,
    PreferenceSessionCreateDTO,
)
from .auth import (
    LoginRequestDTO,
    RegisterRequestDTO,
    TokenPairDTO,
    TokenPayloadDTO,
    RefreshTokenRequestDTO,
    YandexAuthDTO,
    AuthResponseDTO,
)
from .cellar import CellarItemDTO, CellarItemCreateDTO, CellarDeleteResponseDTO
from .scan import EvaluationResponseDTO, ScanResultDTO, ScanHistoryItemDTO
from .sommelier import (
    OnboardingQuestionDTO,
    OnboardingAnswerDTO,
    OnboardingStateDTO,
    SommelierChatMessageDTO,
    SommelierChatRequestDTO,
    SommelierChatResponseDTO,
)

__all__ = [
    "WineDTO",
    "WineDetailDTO",
    "TasteMatrixDTO",
    "FoodPairingDTO",
    "WineFilterDTO",
    "TasteMatrixSearchDTO",
    "PaginatedWinesDTO",
    "UserDTO",
    "TasteProfileDTO",
    "UserPreferenceHistoryDTO",
    "UserCreateDTO",
    "PreferenceSessionCreateDTO",
    "LoginRequestDTO",
    "RegisterRequestDTO",
    "TokenPairDTO",
    "TokenPayloadDTO",
    "RefreshTokenRequestDTO",
    "YandexAuthDTO",
    "AuthResponseDTO",
    "CellarItemDTO",
    "CellarItemCreateDTO",
    "CellarDeleteResponseDTO",
    "EvaluationResponseDTO",
    "ScanResultDTO",
    "ScanHistoryItemDTO",
    "OnboardingQuestionDTO",
    "OnboardingAnswerDTO",
    "OnboardingStateDTO",
    "SommelierChatMessageDTO",
    "SommelierChatRequestDTO",
    "SommelierChatResponseDTO",
]
