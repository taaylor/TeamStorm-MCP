from http import HTTPStatus

import httpx
import pytest
import respx
from pydantic import SecretStr

from teamstorm_mcp.client import TeamStormClient
from teamstorm_mcp.exceptions import (
    TeamStormAuthenticationError,
    TeamStormBadRequestError,
    TeamStormConflictError,
    TeamStormConnectionError,
    TeamStormInvalidResponseError,
    TeamStormNotFoundError,
    TeamStormPermissionError,
    TeamStormRateLimitError,
    TeamStormServerError,
    TeamStormTimeoutError,
)
from teamstorm_mcp.models import PaginationResponse, TaskUpdate, WorkItem

BASE_URL = "https://teamstorm.example.com/cwm/public/api/v1"
TOKEN = SecretStr("test-secret-token")


def workitem(key: str = "TS-13", name: str = "Example task") -> dict[str, object]:
    return {
        "id": f"id-{key}",
        "key": key,
        "name": name,
        "description": "Requirements",
        "changeDate": "2026-09-16T10:00:00Z",
    }


def comment(
    comment_id: str = "comment-1",
    created_at: str = "2026-09-16T10:00:00Z",
) -> dict[str, object]:
    return {
        "id": comment_id,
        "text": "Comment text",
        "createdAt": created_at,
        "author": {"id": "user-1", "displayName": "Maxim"},
    }


async def no_sleep(delay: float) -> None:
    del delay


@respx.mock
async def test_get_workitem_builds_url_and_authorization_header() -> None:
    route = respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        return_value=httpx.Response(200, json=workitem())
    )

    async with TeamStormClient("https://teamstorm.example.com/", TOKEN) as client:
        result = await client.get_workitem("TS", "TS-13")

    assert result.key == "TS-13"
    assert result.change_date is not None
    assert route.calls[0].request.headers["Authorization"] == "PrivateToken test-secret-token"
    assert "//cwm" not in str(route.calls[0].request.url)


@respx.mock
async def test_collection_endpoints_parse_official_response_shapes() -> None:
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/attributes").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "attribute-1",
                        "name": "Acceptance Criteria",
                        "description": "Required behaviour",
                        "type": "UniString",
                        "value": "Works",
                    }
                ]
            },
        )
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    comment("comment-2", "2026-09-16T11:00:00Z"),
                    comment("comment-1", "2026-09-16T10:00:00Z"),
                ]
            },
        )
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/attachments").mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "attachmentId": "attachment-1",
                        "workspaceId": "workspace-1",
                        "fileId": "file-1",
                        "name": "requirements.pdf",
                        "type": "application/pdf",
                        "size": 123,
                    }
                ]
            },
        )
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13/links").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "link-1",
                    "type": {"id": "type-1", "name": "Relates"},
                    "linkedWorkitem": workitem("TS-12", "Related"),
                }
            ],
        )
    )
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/by-parent/TS-13").mock(
        return_value=httpx.Response(200, json=[workitem("TS-14", "Child")])
    )

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        attributes = await client.get_workitem_attributes("TS", "TS-13")
        comments = await client.get_comments("TS", "TS-13")
        attachments = await client.get_attachments("TS", "TS-13")
        links = await client.get_links("TS", "TS-13")
        children = await client.get_children("TS", "TS-13")

    assert attributes[0].value == "Works"
    assert [item.id for item in comments] == ["comment-1", "comment-2"]
    assert attachments[0].name == "requirements.pdf"
    assert links[0].linked_workitem.key == "TS-12"
    assert children[0].key == "TS-14"
    child_request = respx.calls[-1].request
    assert child_request.url.params["withSubItems"] == "false"


@respx.mock
async def test_add_comment_sends_exact_body_and_is_not_retried() -> None:
    route = respx.post(f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments").mock(
        side_effect=httpx.ConnectError("connection lost")
    )

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=no_sleep,
    ) as client:
        with pytest.raises(TeamStormConnectionError):
            await client.add_comment("TS", "TS-13", "  Completed  ")

    assert route.call_count == 1
    assert route.calls[0].request.content == b'{"text":"Completed"}'


async def test_add_comment_rejects_empty_text_before_http() -> None:
    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        with pytest.raises(TeamStormBadRequestError, match="must not be empty"):
            await client.add_comment("TS", "TS-13", "  \n ")


@respx.mock
async def test_update_workitem_uses_limited_patch_body() -> None:
    route = respx.patch(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        return_value=httpx.Response(200, json=workitem(name="Renamed"))
    )

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        result = await client.update_workitem(
            "TS",
            "TS-13",
            TaskUpdate(name="Renamed", status="In Progress"),
        )

    assert result.name == "Renamed"
    assert route.calls[0].request.content == b'{"name":"Renamed","status":"In Progress"}'


async def test_update_workitem_rejects_empty_update() -> None:
    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        with pytest.raises(TeamStormBadRequestError, match="At least one"):
            await client.update_workitem("TS", "TS-13", TaskUpdate())


@pytest.mark.parametrize(
    ("status", "error_type", "attempts"),
    [
        (HTTPStatus.BAD_REQUEST, TeamStormBadRequestError, 1),
        (HTTPStatus.UNAUTHORIZED, TeamStormAuthenticationError, 1),
        (HTTPStatus.FORBIDDEN, TeamStormPermissionError, 1),
        (HTTPStatus.NOT_FOUND, TeamStormNotFoundError, 1),
        (HTTPStatus.CONFLICT, TeamStormConflictError, 1),
        (HTTPStatus.TOO_MANY_REQUESTS, TeamStormRateLimitError, 3),
        (HTTPStatus.INTERNAL_SERVER_ERROR, TeamStormServerError, 1),
        (HTTPStatus.SERVICE_UNAVAILABLE, TeamStormServerError, 3),
    ],
)
@respx.mock
async def test_http_status_mapping(
    status: HTTPStatus,
    error_type: type[Exception],
    attempts: int,
) -> None:
    route = respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        return_value=httpx.Response(status, text="sensitive upstream details")
    )

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=no_sleep,
    ) as client:
        with pytest.raises(error_type) as captured:
            await client.get_workitem("TS", "TS-13")

    assert route.call_count == attempts
    assert "sensitive upstream details" not in str(captured.value)


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (httpx.ReadTimeout("slow"), TeamStormTimeoutError),
        (httpx.ConnectError("offline"), TeamStormConnectionError),
    ],
)
@respx.mock
async def test_transport_errors_are_retried_for_get(
    failure: Exception,
    error_type: type[Exception],
) -> None:
    route = respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        side_effect=failure
    )

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=no_sleep,
    ) as client:
        with pytest.raises(error_type):
            await client.get_workitem("TS", "TS-13")

    assert route.call_count == 3


@respx.mock
async def test_get_retries_transient_status_and_honors_retry_after() -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    route = respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": "0.25"}),
            httpx.Response(200, json=workitem()),
        ]
    )

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=record_sleep,
    ) as client:
        result = await client.get_workitem("TS", "TS-13")

    assert result.key == "TS-13"
    assert route.call_count == 2
    assert delays == [0.25]


@respx.mock
async def test_invalid_json_returns_typed_error() -> None:
    respx.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13").mock(
        return_value=httpx.Response(200, text="not json")
    )

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        with pytest.raises(TeamStormInvalidResponseError):
            await client.get_workitem("TS", "TS-13")


@respx.mock
async def test_paginate_is_bounded_and_uses_tokens() -> None:
    route = respx.get(f"{BASE_URL}/workspaces/TS/workitems").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"items": [workitem("TS-1")], "nextToken": "page-2"},
            ),
            httpx.Response(
                200,
                json={"items": [workitem("TS-2"), workitem("TS-3")]},
            ),
        ]
    )

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        result = await client._paginate(
            "workspaces/TS/workitems",
            PaginationResponse[WorkItem],
            resource="tasks",
            maximum=2,
        )

    assert [item.key for item in result] == ["TS-1", "TS-2"]
    assert route.call_count == 2
    assert route.calls[0].request.url.params["maxItemsCount"] == "2"
    assert route.calls[1].request.url.params["fromToken"] == "page-2"
    assert route.calls[1].request.url.params["maxItemsCount"] == "1"
