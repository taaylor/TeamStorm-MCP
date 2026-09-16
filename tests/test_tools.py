import json

import httpx
import pytest
import respx
from fastmcp import Client

from teamstorm_mcp.server import mcp

BASE_URL = "https://teamstorm.example.com/cwm/public/api/v1"


def workitem() -> dict[str, object]:
    return {
        "id": "task-1",
        "key": "TS-13",
        "name": "Implement MCP",
        "description": "Requirements",
    }


@pytest.fixture(autouse=True)
def teamstorm_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEAMSTORM_URL", "https://teamstorm.example.com")
    monkeypatch.setenv("TEAMSTORM_TOKEN", "test-token")
    monkeypatch.setenv("TEAMSTORM_TIMEOUT", "1")


async def test_tool_discovery_exposes_only_scoped_operations() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()

    tools = {tool.name: tool for tool in result}
    assert set(tools) == {
        "teamstorm_get_task",
        "teamstorm_get_task_context",
        "teamstorm_get_comments",
        "teamstorm_add_comment",
        "teamstorm_get_attachments",
        "teamstorm_get_links",
        "teamstorm_update_task",
        "teamstorm_set_task_description",
    }
    assert tools["teamstorm_get_task"].annotations.readOnlyHint is True
    assert tools["teamstorm_add_comment"].annotations.readOnlyHint is False
    assert tools["teamstorm_add_comment"].annotations.idempotentHint is False
    assert tools["teamstorm_update_task"].annotations.idempotentHint is True
    assert tools["teamstorm_set_task_description"].annotations.idempotentHint is True
    assert all("delete" not in name for name in tools)


@respx.mock
async def test_task_context_tool_returns_text_and_structured_output() -> None:
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        return_value=httpx.Response(200, json=workitem())
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/attributes").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/attachments").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/links").mock(
        return_value=httpx.Response(200, json=[])
    )

    async with Client(mcp) as client:
        result = await client.call_tool("teamstorm_get_task_context", {"task_key": "TS-13"})

    assert result.is_error is False
    assert result.content[0].text.startswith("TeamStorm task context")
    assert result.structured_content is not None
    assert result.structured_content["key"] == "TS-13"
    assert result.structured_content["task"]["name"] == "Implement MCP"


@respx.mock
async def test_expected_domain_error_is_returned_as_mcp_tool_error() -> None:
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-404").mock(return_value=httpx.Response(404))

    async with Client(mcp) as client:
        result = await client.call_tool(
            "teamstorm_get_task",
            {"task_key": "TS-404"},
            raise_on_error=False,
        )

    assert result.is_error is True
    assert "not found" in result.content[0].text.lower()


@respx.mock
async def test_comment_tool_preserves_non_idempotent_single_post() -> None:
    route = respx.post(f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "comment-1",
                "text": "Implemented and verified",
                "createdAt": "2026-09-16T10:00:00Z",
            },
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "teamstorm_add_comment",
            {"task_key": "TS-13", "text": "Implemented and verified"},
        )

    assert result.is_error is False
    assert route.call_count == 1


@respx.mock
async def test_set_task_description_tool_sends_canonical_html() -> None:
    route = respx.patch(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        return_value=httpx.Response(
            200,
            json={
                **workitem(),
                "description": "updated",
            },
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "teamstorm_set_task_description",
            {
                "task_key": "TS-13",
                "task_summary": "Support <safe> descriptions",
                "work_done": ["Added renderer", "Added tests"],
            },
        )

    assert result.is_error is False
    assert json.loads(route.calls[0].request.read()) == {
        "description": (
            "<h2>Суть задачи</h2>\n"
            "<p>Support &lt;safe&gt; descriptions</p>\n"
            "<hr>\n"
            "<h2>Что было сделано</h2>\n"
            "<ul>\n"
            "<li>Added renderer</li>\n"
            "<li>Added tests</li>\n"
            "</ul>"
        )
    }
