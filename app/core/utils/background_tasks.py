import asyncio
from typing import Callable, Any


class WebSocketBackgroundTasks:
    """
    Mimics FastAPI's BackgroundTasks for WebSocket contexts.
    Executes tasks immediately using asyncio.create_task.
    """
    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        asyncio.create_task(func(*args, **kwargs))
