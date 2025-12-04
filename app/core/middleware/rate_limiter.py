# app/core/middleware/limiter.py

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class WebSocketRateLimiter:
    def __init__(self, redis, limit: int, window: int = 60):
        self.redis = redis
        self.limit = limit
        self.window = window

    async def is_allowed(self, key: str) -> bool:
        """
        Check if the action is allowed for the given key.
        Uses a fixed window counter.
        """
        current_count = await self.redis.incr(key)
        if current_count == 1:
            await self.redis.expire(key, self.window)
        
        return current_count <= self.limit

