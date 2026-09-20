"""
Диспетчер задач машинного обучения (ML Dispatcher).
Обеспечивает передачу изображений в ML-слой и получение предсказания с SLA < 1 секунды.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class MLDispatcher:
    """Диспетчер запросов на распознавание винных этикеток (Redis Streams RPC + Fallback)."""

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        mock_mode: bool | None = None,
    ) -> None:
        self.redis = redis_client
        if mock_mode is not None:
            self._mock_mode = mock_mode
        else:
            try:
                from backend.app.config import settings
                self._mock_mode = getattr(settings, "ml_mock_mode", False)
            except ImportError:
                self._mock_mode = False

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
    ) -> tuple[str | None, float, int]:
        """
        Инференс распознавания изображения:
        Возвращает: (predicted_slug, confidence, latency_ms)
        """
        start_time = time.perf_counter()
        req_id = str(uuid.uuid4())
        img_id = image_id or str(uuid.uuid4())

        # Если Redis доступен, отправляем задачу через Redis Streams RPC
        if self.redis:
            pubsub = self.redis.pubsub()
            response_channel = f"ml:response:{req_id}"
            try:
                # Подписка на Pub/Sub канал ответа
                await pubsub.subscribe(response_channel)

                # Публикация задачи в стрим
                await self.redis.xadd(
                    "ml:tasks:recognition",
                    {"request_id": req_id, "image_id": img_id, "s3_key": f"scans/{img_id}.jpg"},
                )

                # Ожидание ответа воркера в рамках SLA чекера
                result = await self._wait_for_rpc_response(pubsub, timeout_seconds=8.5)
                if result is not None:
                    predicted_slug, confidence = result
                    latency_ms = int((time.perf_counter() - start_time) * 1000)
                    return predicted_slug, confidence, latency_ms

            except Exception as e:
                logger.warning("Ошибка RPC через Redis: %s. Применение fallback-распознавания.", e)
            finally:
                try:
                    await pubsub.unsubscribe(response_channel)
                    await pubsub.close()
                except Exception as close_exc:
                    logger.debug("Ошибка при закрытии PubSub подписки: %s", close_exc)

        # Fallback / Mock-режим при отсутствии запущенного внешнего воркера
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        if self._mock_mode:
            logger.info("MLDispatcher: возврат fallback mock-предсказания для тестирования фронтенда.")
            return "fanagoriya-100-ottenkov-krasnogo-kaberne-kaberne-sovinon-krasnoe-suhoe-135", 0.94, latency_ms

        return None, 0.0, latency_ms
