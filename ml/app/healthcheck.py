import sys
import time
import redis

from app.config import settings


def check_health() -> int:
    """
    Health check script for ML Worker container.
    Verifies:
    1. Redis connectivity
    2. Active worker heartbeat freshness (< 20s)
    """
    try:
        r = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True,
            socket_timeout=3.0,
        )
        if not r.ping():
            print("ERROR: Redis ping failed", file=sys.stderr)
            return 1

        heartbeat_keys = r.keys("ml:worker:heartbeat:*")
        if not heartbeat_keys:
            print("ERROR: No active ML worker heartbeats found in Redis", file=sys.stderr)
            return 1

        latest_timestamp = 0.0
        for key in heartbeat_keys:
            val = r.get(key)
            if val:
                try:
                    latest_timestamp = max(latest_timestamp, float(val))
                except ValueError:
                    pass

        age = time.time() - latest_timestamp
        if age > 20.0:
            print(f"ERROR: ML worker heartbeat is stale ({age:.1f}s old)", file=sys.stderr)
            return 1

        print(f"OK: ML Worker is active (heartbeat {age:.1f}s ago)")
        return 0

    except Exception as exc:
        print(f"ERROR: Healthcheck exception: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(check_health())
