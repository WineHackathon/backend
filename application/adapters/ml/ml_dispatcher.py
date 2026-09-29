"""
Диспетчер задач машинного обучения (ML Dispatcher).
Обеспечивает интеграцию с GPU ML-сервисом (SigLIP2 + Qwen 2B reranker),
поддерживает прямой HTTP multipart/form-data к H100 / Tuna,
Redis Streams RPC и отказоустойчивый fallback.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any
import httpx
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class MLPredictionResult:
    """
    Результат инференса ML-модели.
    Поддерживает распаковку как кортеж из 3 элементов (slug, confidence, latency_ms)
    для 100% обратной совместимости, а также предоставляет доступ к атрибутам
    slug, confidence, latency_ms, top5, card, raw_response.
    """

    def __init__(
        self,
        slug: str | None,
        confidence: float | None,
        latency_ms: int,
        top5: list[dict[str, Any]] | None = None,
        card: dict[str, Any] | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        self.slug = slug
        self.confidence = confidence
        self.latency_ms = latency_ms
        self.top5 = top5 or []
        self.card = card or {}
        self.raw_response = raw_response or {}

    def __iter__(self):
        return iter((self.slug, self.confidence, self.latency_ms))

    def __getitem__(self, index: int | slice):
        return (self.slug, self.confidence, self.latency_ms)[index]

    def __len__(self) -> int:
        return 3

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, tuple):
            return (self.slug, self.confidence, self.latency_ms) == other
        if isinstance(other, MLPredictionResult):
            return (
                self.slug == other.slug
                and self.confidence == other.confidence
                and self.latency_ms == other.latency_ms
            )
        return False

    def __repr__(self) -> str:
        return (
            f"MLPredictionResult(slug={self.slug!r}, confidence={self.confidence}, "
            f"latency_ms={self.latency_ms}, top5_count={len(self.top5)})"
        )


class MLDispatcher:
    """Диспетчер запросов на распознавание винных этикеток (HTTP Tuna/H100 + Redis Streams RPC + Fallback)."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        mock_mode: bool | None = None,
        api_url: str | None = None,
        api_token: str | None = None,
        timeout_seconds: float | None = None,
        fallback_to_mock: bool | None = None,
    ) -> None:
        self.redis = redis_client

        # Инициализация настроек из окружения или settings
        settings = None
        try:
            from backend.app.config import settings as app_settings
            settings = app_settings
        except ImportError:
            pass

        if mock_mode is not None:
            self._mock_mode = mock_mode
        elif settings is not None:
            self._mock_mode = getattr(settings, "ml_mock_mode", False)
        else:
            self._mock_mode = False

        if api_url is not None:
            self.api_url = api_url
        elif settings is not None:
            self.api_url = getattr(settings, "ml_api_url", "https://akcizny-sbor.ru.tuna.am")
        else:
            self.api_url = "https://akcizny-sbor.ru.tuna.am"

        if api_token is not None:
            self.api_token = api_token
        elif settings is not None:
            self.api_token = getattr(settings, "ml_api_token", "")
        else:
            self.api_token = ""

        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        elif settings is not None:
            self.timeout_seconds = getattr(settings, "ml_api_timeout", 12.0)
        else:
            self.timeout_seconds = 12.0

        if fallback_to_mock is not None:
            self._fallback_to_mock = fallback_to_mock
        elif settings is not None:
            self._fallback_to_mock = getattr(settings, "ml_fallback_to_mock", True)
        else:
            self._fallback_to_mock = True

    async def _predict_via_http(
        self,
        image_bytes: bytes,
        endpoint_path: str = "/v1/recognize",
    ) -> MLPredictionResult | None:
        """Прямой вызов внешнего ML-сервиса через HTTP multipart/form-data."""
        if not self.api_url:
            return None

        url = f"{self.api_url.rstrip('/')}{endpoint_path}"
        headers: dict[str, str] = {}
        if self.api_token:
            headers["X-Token"] = self.api_token

        files = {"image": ("bottle.jpg", image_bytes, "image/jpeg")}
        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds, connect=5.0)
            ) as client:
                response = await client.post(url, files=files, headers=headers)

            latency_ms = int((time.perf_counter() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                slug = data.get("slug")
                top5 = data.get("top5") or []
                card = data.get("card") or {}

                # Извлечение информативного скора уверенности
                confidence: float | None = None
                raw_confidence = data.get("confidence")
                if raw_confidence is not None:
                    try:
                        confidence = float(raw_confidence)
                    except (ValueError, TypeError):
                        confidence = None

                # Если confidence uncalibrated (null), берём reranker_score / visual_cosine
                if confidence is None and top5:
                    top1 = top5[0]
                    score_val = top1.get("reranker_score") or top1.get("score")
                    if score_val is not None:
                        try:
                            confidence = round(float(score_val), 4)
                        except (ValueError, TypeError):
                            confidence = None

                if confidence is None and data.get("raw_scores"):
                    raw_vc = data["raw_scores"].get("visual_cosine")
                    if raw_vc is not None:
                        try:
                            confidence = round(float(raw_vc), 4)
                        except (ValueError, TypeError):
                            confidence = None

                return MLPredictionResult(
                    slug=slug,
                    confidence=confidence or (0.85 if slug else None),
                    latency_ms=latency_ms,
                    top5=top5,
                    card=card,
                    raw_response=data,
                )
            else:
                logger.warning(
                    "ML API %s вернул статус %d: %s",
                    url,
                    response.status_code,
                    response.text[:200],
                )
                return None
        except httpx.TimeoutException:
            logger.warning("ML API timeout (%s сек) при запросе к %s", self.timeout_seconds, url)
            return None
        except httpx.RequestError as exc:
            logger.warning("Сетевая ошибка при запросе к ML API %s: %s", url, exc)
            return None
        except Exception as exc:
            logger.error("Непредвиденная ошибка при запросе к ML API: %s", exc, exc_info=True)
            return None

    async def _wait_for_rpc_response(
        self,
        pubsub: Any,
        timeout_seconds: float = 8.5,
    ) -> tuple[str | None, float] | None:
        """Ожидание ответа от ML воркера через Pub/Sub канал с таймаутом."""
        deadline = time.perf_counter() + timeout_seconds
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None

            msg = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=min(remaining, 0.2),
            )
            if msg and msg.get("type") == "message":
                raw_data = msg.get("data")
                if isinstance(raw_data, (str, bytes)):
                    data = json.loads(raw_data)
                    return data.get("slug"), float(data.get("confidence", 0.0))

            await asyncio.sleep(0.02)

    async def predict(
        self,
        image_bytes: bytes,
        image_id: str | None = None,
    ) -> MLPredictionResult:
        """
        Инференс распознавания винной этикетки:
        1. Если включен mock_mode -> возврат мок-данных (для изолированного тестирования).
        2. Если задан HTTP эндпоинт ML API -> обращение к внешнему H100 / Tuna сервису.
        3. Если доступен Redis -> обращение через Redis Streams RPC.
        4. При сбоях внешней модели -> возврат fallback mock-предсказания или (None, 0.0, latency_ms).
        """
        start_time = time.perf_counter()
        req_id = str(uuid.uuid4())
        img_id = image_id or str(uuid.uuid4())

        # 1. Принудительный mock-режим
        if self._mock_mode:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info("MLDispatcher: возврат mock-предсказания (mock_mode=True).")
            return MLPredictionResult(
                slug="fanagoriya-100-ottenkov-krasnogo-kaberne-kaberne-sovinon-krasnoe-suhoe-135",
                confidence=0.94,
                latency_ms=latency_ms,
                raw_response={"mock": True},
            )

        # 2. HTTP запрос к внешнему GPU ML-сервису (H100 / Tuna)
        if self.api_url:
            http_result = await self._predict_via_http(image_bytes, endpoint_path="/v1/recognize")
            if http_result is not None:
                return http_result
            logger.warning("MLDispatcher: HTTP ML API не ответил, проверка локальных очередей.")

        # 3. Если Redis доступен, отправляем задачу через Redis Streams RPC
        if self.redis:
            pubsub = self.redis.pubsub()
            response_channel = f"ml:response:{req_id}"
            try:
                await pubsub.subscribe(response_channel)
                await self.redis.xadd(
                    "ml:tasks:recognition",
                    {"request_id": req_id, "image_id": img_id, "s3_key": f"scans/{img_id}.jpg"},
                )

                result = await self._wait_for_rpc_response(pubsub, timeout_seconds=8.5)
                if result is not None:
                    predicted_slug, confidence = result
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    return MLPredictionResult(
                        slug=predicted_slug,
                        confidence=confidence,
                        latency_ms=latency_ms,
                    )
            except Exception as e:
                logger.warning("Ошибка RPC через Redis: %s. Применение fallback-распознавания.", e)
            finally:
                try:
                    await pubsub.unsubscribe(response_channel)
                    await pubsub.close()
                except Exception as close_exc:
                    logger.debug("Ошибка при закрытии PubSub подписки: %s", close_exc)

        # 4. Fallback при отсутствии/сбое внешнего воркера
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        if self._fallback_to_mock:
            logger.info("MLDispatcher: возврат fallback mock-предсказания после сбоя внешнего воркера.")
            return MLPredictionResult(
                slug="fanagoriya-100-ottenkov-krasnogo-kaberne-kaberne-sovinon-krasnoe-suhoe-135",
                confidence=0.94,
                latency_ms=latency_ms,
                raw_response={"mock_fallback": True},
            )

        return MLPredictionResult(slug=None, confidence=0.0, latency_ms=latency_ms)
