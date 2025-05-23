"""Redis utilities for real-time updates and message passing."""

import json
from typing import TYPE_CHECKING, Any, Dict, Optional

try:
    import aioredis  # type: ignore
except ImportError:  # pragma: no cover - optional
    aioredis = None

from hydrobot.utils.logger_setup import get_logger

log = get_logger(__name__)


# Lazy import of settings to avoid circular dependencies
def get_settings():
    from hydrobot.config.settings import settings

    return settings


if TYPE_CHECKING:
    from hydrobot.config.settings import RedisSettings


class RedisPublisher:
    """Handles publishing updates to Redis channels."""

    def __init__(self):
        """Initialize Redis publisher."""
        self.redis: Optional[aioredis.Redis] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Redis server.

        Returns:
            True if connection successful
        """
        if aioredis is None:
            log.warning("aioredis not installed; Redis features disabled")
            return False
        try:
            settings = get_settings()  # Get settings dynamically
            redis_url = f"redis://{settings.redis.host}:{settings.redis.port}"
            if settings.redis.password:
                redis_url = f"redis://:{settings.redis.password.get_secret_value()}@{settings.redis.host}:{settings.redis.port}"

            self.redis = await aioredis.from_url(
                redis_url, db=settings.redis.db, encoding="utf-8", decode_responses=True
            )
            self._connected = True
            log.info("Connected to Redis")
            return True

        except Exception as e:
            log.error("Redis connection failed", error=str(e))
            return False

    async def publish(self, channel: str, data: Dict[str, Any]) -> bool:
        """Publish message to Redis channel.

        Args:
            channel: Redis channel name
            data: Message data to publish

        Returns:
            True if publish successful
        """
        try:
            if not self._connected or not self.redis:
                if not await self.connect():
                    return False

            message = json.dumps(data)
            await self.redis.publish(channel, message)
            return True

        except Exception as e:
            log.error("Redis publish failed", channel=channel, error=str(e))
            return False

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
        self._connected = False
