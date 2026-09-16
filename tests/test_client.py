from http import HTTPStatus

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from aioresponses import aioresponses
from pydantic import SecretStr
from yarl import URL

from teamstorm_mcp.adapters.teamstorm.client import TeamStormClient
from teamstorm_mcp.adapters.teamstorm.schemas import PaginationResponse
from teamstorm_mcp.application.exceptions import (
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
from teamstorm_mcp.application.models import TaskUpdate, WorkItem

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


async def test_get_workitem_builds_url_and_authorization_header(
    http_mock: aioresponses,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13", status=200, payload=workitem())

    async with TeamStormClient("https://teamstorm.example.com/", TOKEN) as client:
        result = await client.get_workitem("TS", "TS-13")

    assert result.key == "TS-13"
    assert result.change_date is not None
    assert (
        http_mock.requests[("GET", URL(url))][0].kwargs["headers"]["Authorization"]
        == "PrivateToken test-secret-token"
    )
    assert "//cwm" not in url


async def test_collection_endpoints_parse_official_response_shapes(
    http_mock: aioresponses,
) -> None:
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/attributes",
        status=200,
        payload={
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
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments",
        status=200,
        payload={
            "items": [
                comment("comment-2", "2026-09-16T11:00:00Z"),
                comment("comment-1", "2026-09-16T10:00:00Z"),
            ]
        },
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/attachments",
        status=200,
        payload={
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
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/links",
        status=200,
        payload=[
            {
                "id": "link-1",
                "type": {"id": "type-1", "name": "Relates"},
                "linkedWorkitem": workitem("TS-12", "Related"),
            }
        ],
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems/by-parent/TS-13?withSubItems=false",
        status=200,
        payload=[workitem("TS-14", "Child")],
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
    assert (
        "GET",
        URL(f"{BASE_URL}/workspaces/TS/workitems/by-parent/TS-13?withSubItems=false"),
    ) in http_mock.requests


async def test_add_comment_sends_exact_body_and_is_not_retried(
    http_mock: aioresponses,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments"
    http_mock.post(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13/comments",
        exception=aiohttp.ClientConnectionError("connection lost"),
        repeat=True,
    )

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=no_sleep,
    ) as client:
        with pytest.raises(TeamStormConnectionError):
            await client.add_comment("TS", "TS-13", "  Completed  ")

    assert sum(len(calls) for calls in http_mock.requests.values()) == 1
    assert http_mock.requests[("POST", URL(url))][0].kwargs["json"] == {"text": "Completed"}


async def test_add_comment_rejects_empty_text_before_http() -> None:
    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        with pytest.raises(TeamStormBadRequestError, match="must not be empty"):
            await client.add_comment("TS", "TS-13", "  \n ")


async def test_update_workitem_uses_limited_patch_body(
    http_mock: aioresponses,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.patch(
        f"{BASE_URL}/workspaces/TS/workitems/TS-13", status=200, payload=workitem(name="Renamed")
    )

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        result = await client.update_workitem(
            "TS",
            "TS-13",
            TaskUpdate(name="Renamed", status="In Progress"),
        )

    assert result.name == "Renamed"
    assert http_mock.requests[("PATCH", URL(url))][0].kwargs["json"] == {
        "name": "Renamed",
        "status": "In Progress",
    }


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
async def test_http_status_mapping(
    http_mock: aioresponses,
    status: HTTPStatus,
    error_type: type[Exception],
    attempts: int,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.get(
        url,
        status=status,
        body="sensitive upstream details",
        repeat=True,
    )

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=no_sleep,
    ) as client:
        with pytest.raises(error_type) as captured:
            await client.get_workitem("TS", "TS-13")

    assert sum(len(calls) for calls in http_mock.requests.values()) == attempts
    assert "sensitive upstream details" not in str(captured.value)


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        (TimeoutError("slow"), TeamStormTimeoutError),
        (aiohttp.ClientConnectionError("offline"), TeamStormConnectionError),
    ],
)
async def test_transport_errors_are_retried_for_get(
    http_mock: aioresponses,
    failure: Exception,
    error_type: type[Exception],
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.get(url, exception=failure, repeat=True)

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=no_sleep,
    ) as client:
        with pytest.raises(error_type):
            await client.get_workitem("TS", "TS-13")

    assert sum(len(calls) for calls in http_mock.requests.values()) == 3


async def test_get_retries_transient_status_and_honors_retry_after(
    http_mock: aioresponses,
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.get(url, status=503, headers={"Retry-After": "0.25"})
    http_mock.get(url, status=200, payload=workitem())

    async with TeamStormClient(
        "https://teamstorm.example.com",
        TOKEN,
        sleep=record_sleep,
    ) as client:
        result = await client.get_workitem("TS", "TS-13")

    assert result.key == "TS-13"
    assert sum(len(calls) for calls in http_mock.requests.values()) == 2
    assert delays == [0.25]


async def test_invalid_json_returns_typed_error(
    http_mock: aioresponses,
) -> None:
    http_mock.get(f"{BASE_URL}/workspaces/TS/workitems/TS-13", status=200, body="not json")

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        with pytest.raises(TeamStormInvalidResponseError):
            await client.get_workitem("TS", "TS-13")


async def test_paginate_is_bounded_and_uses_tokens(
    http_mock: aioresponses,
) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems"
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems?maxItemsCount=2",
        status=200,
        payload={"items": [workitem("TS-1")], "nextToken": "page-2"},
    )
    http_mock.get(
        f"{BASE_URL}/workspaces/TS/workitems?maxItemsCount=1&fromToken=page-2",
        status=200,
        payload={"items": [workitem("TS-2"), workitem("TS-3")]},
    )

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        result = await client._paginate(
            "workspaces/TS/workitems",
            PaginationResponse[WorkItem],
            resource="tasks",
            maximum=2,
        )

    assert [item.key for item in result] == ["TS-1", "TS-2"]
    assert sum(len(calls) for calls in http_mock.requests.values()) == 2
    assert ("GET", URL(f"{url}?maxItemsCount=2")) in http_mock.requests
    assert ("GET", URL(f"{url}?fromToken=page-2&maxItemsCount=1")) in http_mock.requests


@pytest.mark.parametrize("redirect", [False, True])
async def test_real_http_session_reuses_connections_and_closes(redirect: bool) -> None:
    requests: list[web.Request] = []

    async def handle(request: web.Request) -> web.Response:
        requests.append(request)
        if redirect:
            return web.Response(status=302, headers={"Location": "/unexpected"})
        return web.json_response(workitem())

    app = web.Application()
    app.router.add_get("/cwm/public/api/v1/workspaces/TS/workitems/TS-13", handle)
    async with TestServer(app) as server:
        client = TeamStormClient(str(server.make_url("/")), TOKEN)
        try:
            async with client:
                session = client._session
                assert session is not None
                for _ in range(2):
                    result = await client.get_workitem("TS", "TS-13")
                    assert result.key == "TS-13"
        except TeamStormBadRequestError as exc:
            assert redirect
            assert "HTTP 302" in str(exc)
        else:
            assert not redirect

        assert session.closed
        assert len(requests) == (1 if redirect else 2)
        assert all(r.headers["Authorization"] == "PrivateToken test-secret-token" for r in requests)
        assert all(r.headers["Accept"] == "application/json" for r in requests)
        if not redirect:
            assert requests[0].transport is requests[1].transport


@pytest.mark.parametrize("failure", [None, TimeoutError("slow")])
async def test_patch_is_not_retried(http_mock: aioresponses, failure: Exception | None) -> None:
    url = f"{BASE_URL}/workspaces/TS/workitems/TS-13"
    http_mock.patch(url, status=503, exception=failure, repeat=True)
    error_type = TeamStormTimeoutError if failure else TeamStormServerError

    async with TeamStormClient("https://teamstorm.example.com", TOKEN) as client:
        with pytest.raises(error_type):
            await client.update_workitem("TS", "TS-13", TaskUpdate(name="Updated"))

    assert len(http_mock.requests[("PATCH", URL(url))]) == 1
