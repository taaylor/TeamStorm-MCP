from pathlib import Path

import pytest
from aioresponses import aioresponses
from fastmcp import Client
from yarl import URL

from teamstorm_mcp.bootstrap import mcp

BASE_URL = "https://teamstorm.example.com/cwm/public/api/v1"


def workitem() -> dict[str, object]:
    return {
        "id": "task-1",
        "key": "TS-13",
        "name": "Implement MCP",
        "description": "Requirements",
    }


@pytest.fixture(autouse=True)
def teamstorm_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TEAMSTORM_URL", "https://teamstorm.example.com")
    monkeypatch.setenv("TEAMSTORM_TOKEN", "test-token")
    monkeypatch.setenv("TEAMSTORM_TIMEOUT", "1")
    monkeypatch.setenv("TEAMSTORM_QUEUE_PATH", str(tmp_path / "queue.sqlite3"))


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
        "teamstorm_get_task_pages",
        "teamstorm_update_task",
        "teamstorm_set_task_description",
        "teamstorm_schedule_task_closure",
        "teamstorm_get_task_closure",
        "teamstorm_get_workflow",
        "teamstorm_cancel_task_closure",
    }
    expected_annotations = {
        "teamstorm_get_task": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_get_task_context": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_get_comments": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_add_comment": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "teamstorm_get_attachments": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_get_links": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_get_task_pages": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_update_task": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_set_task_description": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_schedule_task_closure": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_get_task_closure": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_get_workflow": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
        "teamstorm_cancel_task_closure": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    }
    assert {
        name: tool.annotations.model_dump(exclude_unset=True) for name, tool in tools.items()
    } == expected_annotations
    assert all("delete" not in name for name in tools)


async def test_task_context_tool_returns_text_and_structured_output(
    http_mock: aioresponses,
) -> None:
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13", status=200, payload=workitem())
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/attributes", status=200, payload={"items": []}
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments", status=200, payload={"items": []}
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/attachments", status=200, payload={"items": []}
    )
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/links", status=200, payload=[])

    async with Client(mcp) as client:
        result = await client.call_tool("teamstorm_get_task_context", {"task_key": "TS-13"})

    assert result.is_error is False
    assert result.content[0].text.startswith("TeamStorm task context")
    assert result.structured_content is not None
    assert result.structured_content["key"] == "TS-13"
    assert result.structured_content["task"]["name"] == "Implement MCP"


async def test_task_pages_tool_returns_linked_pages_and_content(
    http_mock: aioresponses,
) -> None:
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13", status=200, payload=workitem())
    http_mock.get(
        f"{BASE_URL}/workspaces?maxItemsCount=200",
        status=200,
        payload={"items": [{"id": "workspace-1", "key": "TS", "name": "TS"}]},
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/documents?maxItemsCount=200",
        status=200,
        payload={
            "items": [
                {
                    "workspaceId": "workspace-1",
                    "id": "page-1",
                    "key": "DOC-1",
                    "name": "Architecture",
                    "documentUrl": "/documents/DOC-1",
                    "content": "Architecture details",
                }
            ]
        },
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/documents/DOC-1/workitem-links",
        status=200,
        payload=[workitem()],
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "teamstorm_get_task_pages",
            {"task_key": "TS-13", "include_content": True, "max_items": 10},
        )

    assert result.is_error is False
    assert result.content[0].text.startswith("TeamStorm linked pages")
    assert result.structured_content is not None
    assert result.structured_content["taskKey"] == "TS-13"
    assert result.structured_content["pages"][0]["key"] == "DOC-1"
    assert result.structured_content["pages"][0]["content"] == "Architecture details"


async def test_schedule_can_be_read_in_another_mcp_session(http_mock: aioresponses) -> None:
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13", payload=workitem())
    async with Client(mcp) as client:
        scheduled = await client.call_tool(
            "teamstorm_schedule_task_closure",
            {"task_key": "TS-13", "close_at": "2026-09-17T18:00:00+05:00", "target_status": "Done"},
        )
    async with Client(mcp) as client:
        saved = await client.call_tool("teamstorm_get_task_closure", {"task_key": "TS-13"})
    assert scheduled.is_error is False
    assert saved.structured_content is not None
    assert saved.structured_content["result"] == scheduled.structured_content
    assert saved.structured_content["result"]["state"] == "pending"
    assert all(method == "GET" for method, _ in http_mock.requests)


async def test_expected_domain_error_is_returned_as_mcp_tool_error(
    http_mock: aioresponses,
) -> None:
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-404", status=404)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "teamstorm_get_task",
            {"task_key": "TS-404"},
            raise_on_error=False,
        )

    assert result.is_error is True
    assert "not found" in result.content[0].text.lower()


async def test_comment_tool_preserves_non_idempotent_single_post(
    http_mock: aioresponses,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments"
    http_mock.post(
        url,
        status=200,
        payload={
            "id": "comment-1",
            "text": "Implemented and verified",
            "createdAt": "2026-09-16T10:00:00Z",
        },
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "teamstorm_add_comment",
            {"task_key": "TS-13", "text": "Implemented and verified"},
        )

    assert result.is_error is False
    assert sum(len(calls) for calls in http_mock.requests.values()) == 1


async def test_set_task_description_tool_sends_canonical_html(
    http_mock: aioresponses,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.patch(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13",
        status=200,
        payload={
            **workitem(),
            "description": "updated",
        },
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
    assert http_mock.requests[("PATCH", URL(url))][0].kwargs["json"] == {
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
