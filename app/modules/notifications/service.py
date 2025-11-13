# app/modules/notifications/service.py

from abc import ABC, abstractmethod
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from fastapi import BackgroundTasks

from app.modules.shared.enums import NotificationType

if TYPE_CHECKING:
    from fastapi import UploadFile


class NotificationService(ABC):
    """Abstract base class for all notification channels."""

    @abstractmethod
    async def send(self, notification_type: NotificationType, recipients: list[str], context: Optional[dict] = None, attachments: Optional[list["UploadFile"]] = None):
        pass

    async def schedule(
        self,
        send_func: Callable[..., Awaitable[None]],
        background_tasks: Optional[BackgroundTasks] = None,
        **kwargs
    ):
        if background_tasks:
            background_tasks.add_task(send_func, **kwargs)
        else:
            await send_func(**kwargs)