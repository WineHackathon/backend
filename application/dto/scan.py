"""
DTO схемы для процесса сканирования этикеток и чекера хакатона.
"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from application.dto.wine import WineDTO


class EvaluationResponseDTO(BaseModel):
    """
    Ответ эндпоинта /v1/eval/predict в точном соответствии со спецификацией participant_test.sh.
    """
    slug: str | None = Field(default=None, description="Распознанный слаг вина или null при неуверенности")


class ScanResultDTO(BaseModel):
    """Результат пользовательского сканирования этикетки вина."""
    image_id: str
    slug: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    wine: WineDTO | None = None
    remaining_scans: int | None = Field(default=None, description="Оставшееся число бесплатных сканирований")
    registration_required: bool = Field(default=False, description="Требуется ли регистрация для продолжения")


class ScanHistoryItemDTO(BaseModel):
    """Элемент истории сканирований в личном кабинете."""
    id: uuid.UUID
    image_id: str
    predicted_slug: str | None = None
    confidence: float | None = None
    latency_ms: int | None = None
    status: str
    created_at: datetime
    wine: WineDTO | None = None

    model_config = {"from_attributes": True}
