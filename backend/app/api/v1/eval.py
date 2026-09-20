"""
Эндпоинт чекера хакатона ЛЦТ 2026 (/v1/eval/predict).
Строгое соответствие формату скрипта participant_test.sh.
"""
from fastapi import APIRouter, Depends, File, UploadFile
from application.dto.scan import EvaluationResponseDTO
from backend.app.dependencies import get_ml_dispatcher
from application.adapters.ml.ml_dispatcher import MLDispatcher

router = APIRouter(tags=["Чекер хакатона (Evaluator)"])


@router.post("/v1/eval/predict", response_model=EvaluationResponseDTO, summary="Точка входа чекера хакатона (предсказание по фото)")
async def predict_eval(
    image: UploadFile = File(..., description="Фотография этикетки вина"),
    ml_dispatcher: MLDispatcher = Depends(get_ml_dispatcher),
):
    """
    Эндпоинт для автоматического чекера хакатона:
    Принимает multipart-поле 'image', передает в ML-инференс и возвращает
    {"slug": "..."} или {"slug": null} с задержкой < 1 секунды.
    """
    image_bytes = await image.read()
    slug, confidence, latency_ms = await ml_dispatcher.predict(image_bytes)
    return EvaluationResponseDTO(slug=slug)
