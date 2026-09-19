"""
Сервис ограничения частоты запросов (Rate Limiting) для анонимных пользователей.
Защита по X-Device-Fingerprint и IP-адресу через атомарный счетчик Redis.
"""
import logging
import redis.asyncio as redis
from backend.app.config import settings

logger = logging.getLogger(__name__)


class ScanRateLimiter:
    """
    Ограничитель бесплатных сканирований для неавторизованных пользователей.
    Предоставляет до 5 бесплатных сканирований на одно устройство/IP.
    После исчерпания возвращает требование регистрации.
    """

    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis = redis_client
        self.limit = settings.anon_scan_limit
        self.ttl = settings.anon_scan_ttl_seconds

    async def check_and_increment(
        self,
        fingerprint: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[bool, int]:
        """
        Проверка лимита и инкремент счетчика.
        Возвращает:
        - allowed (bool): разрешено ли сканирование.
        - remaining (int): оставшееся число бесплатных сканирований.
        """
        # Если клиент не подключен (например, в изолированных тестах без мока), разрешаем
        if not self.redis:
            return True, self.limit

        identifier = fingerprint or ip_address or "unknown_device"
        key = f"anon:scan:{identifier}"

        try:
            # Атомарный инкремент в Redis
            current = await self.redis.incr(key)
            if current == 1:
                # Устанавливаем TTL 24 часа для первой попытки
                await self.redis.expire(key, self.ttl)

            if current <= self.limit:
                remaining = self.limit - current
                return True, remaining
            else:
                return False, 0

        except Exception as exc:
            logger.error(f"Ошибка проверки rate limit в Redis: {exc}. Пропуск проверки.", exc_info=True)
            return True, self.limit
