"""
Экспорт всех DTO схем слоя application.
"""
from .wine import WineDTO, WineDetailDTO, TasteMatrixDTO, FoodPairingDTO
from .user import UserDTO, TasteProfileDTO
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
    "UserDTO",
    "TasteProfileDTO",
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
