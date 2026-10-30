"""In-process task registry for tracking and cancelling background repair jobs."""

import asyncio
from typing import Dict, Optional


class JobRegistry:
    """Manages active asyncio Tasks for in-flight repair jobs."""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}

    def register(self, repair_id: str, task: asyncio.Task) -> None:
        self._tasks[repair_id] = task

    def unregister(self, repair_id: str) -> None:
        self._tasks.pop(repair_id, None)

    def cancel(self, repair_id: str) -> bool:
        task = self._tasks.get(repair_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def is_running(self, repair_id: str) -> bool:
        task = self._tasks.get(repair_id)
        return bool(task and not task.done())


job_registry = JobRegistry()
