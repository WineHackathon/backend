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
from .user import UserDTO, TasteProfileDTO, UserPreferenceHistoryDTO
from .auth import LoginRequestDTO, RegisterRequestDTO, TokenPairDTO, YandexAuthDTO
from .cellar import CellarItemDTO, CellarItemCreateDTO
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
    "LoginRequestDTO",
    "RegisterRequestDTO",
    "TokenPairDTO",
    "YandexAuthDTO",
    "CellarItemDTO",
    "CellarItemCreateDTO",
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
