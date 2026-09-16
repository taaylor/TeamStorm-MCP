from typing import Protocol

from teamstorm_mcp.application.models import WorkItem


class TaskStatusContextProvider(Protocol):
    """Read the task and its current status before a scheduled transition."""

    async def get_task(self, task_key: str) -> WorkItem: ...
