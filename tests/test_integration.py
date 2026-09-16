import os

import pytest
from pydantic import SecretStr

from teamstorm_mcp.client import TeamStormClient
from teamstorm_mcp.service import TeamStormService


@pytest.mark.integration
async def test_real_task_context_is_read_only() -> None:
    url = os.getenv("TEAMSTORM_URL")
    token = os.getenv("TEAMSTORM_TOKEN")
    task_key = os.getenv("TEAMSTORM_TEST_TASK")
    if not all((url, token, task_key)):
        pytest.skip("TEAMSTORM_URL, TEAMSTORM_TOKEN, and TEAMSTORM_TEST_TASK are required")

    assert url is not None
    assert token is not None
    assert task_key is not None
    async with TeamStormClient(url, SecretStr(token)) as client:
        context = await TeamStormService(client).get_task_context(task_key)

    assert context.key == task_key.strip().upper()
    assert context.task.key == context.key
