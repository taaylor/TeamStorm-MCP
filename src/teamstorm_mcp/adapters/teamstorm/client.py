"""Asynchronous client for the TeamStorm public REST API."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from http import HTTPStatus
from typing import TypeVar

import aiohttp
from pydantic import SecretStr, TypeAdapter, ValidationError

from teamstorm_mcp.adapters.teamstorm.constants import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_GET_ATTEMPTS,
    MAX_PAGINATED_ITEMS,
    MAX_RETRY_AFTER_SECONDS,
    PAGINATION_PAGE_SIZE,
    RETRY_BACKOFF_SECONDS,
    RETRYABLE_HTTP_STATUSES,
    TEAMSTORM_API_PATH,
)
from teamstorm_mcp.adapters.teamstorm.schemas import ItemsResponse, PaginationResponse
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
from teamstorm_mcp.application.models import (
    Attachment,
    Comment,
    TaskUpdate,
    WorkItem,
    WorkItemAttribute,
    WorkItemLink,
    WorkspaceReference,
)

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT")


class TeamStormClient:
    """Encapsulate all HTTP communication with TeamStorm."""

    def __init__(
        self,
        base_url: str,
        token: SecretStr,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = f"{base_url.rstrip('/')}{TEAMSTORM_API_PATH}/"
        self._timeout = timeout
        self._sleep = sleep
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"PrivateToken {token.get_secret_value()}",
        }
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                base_url=self._base_url,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers=self._headers,
            )
        return self._session

    async def __aenter__(self) -> "TeamStormClient":
        self._get_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""

        if self._session is not None:
            await self._session.close()

    async def get_workitem(self, workspace: str, workitem: str) -> WorkItem:
        response = await self._request(
            "GET",
            f"workspaces/{workspace}/workitems/{workitem}",
            resource=f"task {workitem}",
        )
        return self._validate(WorkItem, response, resource=f"task {workitem}")

    async def get_workitem_attributes(
        self,
        workspace: str,
        workitem: str,
    ) -> list[WorkItemAttribute]:
        response = await self._request(
            "GET",
            f"workspaces/{workspace}/workitems/{workitem}/attributes",
            resource=f"attributes of task {workitem}",
        )
        envelope = self._validate(
            ItemsResponse[WorkItemAttribute],
            response,
            resource=f"attributes of task {workitem}",
        )
        return envelope.items

    async def get_comments(self, workspace: str, workitem: str) -> list[Comment]:
        response = await self._request(
            "GET",
            f"workspaces/{workspace}/workitems/{workitem}/comments",
            resource=f"comments of task {workitem}",
        )
        envelope = self._validate(
            ItemsResponse[Comment],
            response,
            resource=f"comments of task {workitem}",
        )
        return sorted(envelope.items, key=lambda comment: comment.created_at)

    async def add_comment(self, workspace: str, workitem: str, text: str) -> Comment:
        normalized_text = text.strip()
        if not normalized_text:
            raise TeamStormBadRequestError("A TeamStorm comment must not be empty.")
        response = await self._request(
            "POST",
            f"workspaces/{workspace}/workitems/{workitem}/comments",
            json={"text": normalized_text},
            resource=f"task {workitem}",
        )
        comment = self._validate(Comment, response, resource=f"comment on task {workitem}")
        logger.info("Comment added to %s", workitem)
        return comment

    async def get_attachments(self, workspace: str, workitem: str) -> list[Attachment]:
        response = await self._request(
            "GET",
            f"workspaces/{workspace}/workitems/{workitem}/attachments",
            resource=f"attachments of task {workitem}",
        )
        envelope = self._validate(
            ItemsResponse[Attachment],
            response,
            resource=f"attachments of task {workitem}",
        )
        return envelope.items

    async def get_links(self, workspace: str, workitem: str) -> list[WorkItemLink]:
        response = await self._request(
            "GET",
            f"workspaces/{workspace}/workitems/{workitem}/links",
            resource=f"links of task {workitem}",
        )
        return self._validate_list(
            TypeAdapter(list[WorkItemLink]),
            response,
            resource=f"links of task {workitem}",
        )

    async def get_children(self, workspace: str, workitem: str) -> list[WorkItem]:
        response = await self._request(
            "GET",
            f"workspaces/{workspace}/workitems/by-parent/{workitem}",
            params={"withSubItems": "false"},
            resource=f"children of task {workitem}",
        )
        return self._validate_list(
            TypeAdapter(list[WorkItem]),
            response,
            resource=f"children of task {workitem}",
        )

    async def list_workitems(self) -> list[WorkItem]:
        workspaces = await self._paginate(
            "workspaces",
            PaginationResponse[WorkspaceReference],
            resource="workspaces",
            maximum=None,
        )
        tasks: list[WorkItem] = []
        for workspace in workspaces:
            tasks.extend(
                await self._paginate(
                    f"workspaces/{workspace.key}/workitems",
                    PaginationResponse[WorkItem],
                    resource=f"tasks in {workspace.key}",
                    maximum=None,
                )
            )
        return tasks

    async def _paginate(
        self,
        path: str,
        page_model: type[PaginationResponse[ModelT]],
        *,
        resource: str,
        params: Mapping[str, str] | None = None,
        maximum: int | None = MAX_PAGINATED_ITEMS,
    ) -> list[ModelT]:
        """Load a bounded token-paginated collection for future list endpoints."""

        items: list[ModelT] = []
        next_token: str | None = None
        seen_tokens: set[str] = set()
        while maximum is None or len(items) < maximum:
            page_params = dict(params or {})
            page_params["maxItemsCount"] = str(
                PAGINATION_PAGE_SIZE
                if maximum is None
                else min(PAGINATION_PAGE_SIZE, maximum - len(items))
            )
            if next_token is not None:
                page_params["fromToken"] = next_token

            response = await self._request(
                "GET",
                path,
                params=page_params,
                resource=resource,
            )
            page = self._validate(
                page_model,
                response,
                resource=resource,
            )
            items.extend(page.items if maximum is None else page.items[: maximum - len(items)])
            next_token = page.next_token
            if next_token is None:
                break
            if next_token in seen_tokens:
                raise TeamStormInvalidResponseError(
                    f"TeamStorm returned a repeated pagination token for {resource}."
                )
            seen_tokens.add(next_token)
        return items

    async def update_workitem(
        self,
        workspace: str,
        workitem: str,
        update: TaskUpdate,
    ) -> WorkItem:
        body = update.model_dump(exclude_none=True)
        if not body:
            raise TeamStormBadRequestError("At least one task field must be provided for update.")
        response = await self._request(
            "PATCH",
            f"workspaces/{workspace}/workitems/{workitem}",
            json=body,
            resource=f"task {workitem}",
        )
        return self._validate(WorkItem, response, resource=f"task {workitem}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Mapping[str, object] | None = None,
        resource: str,
    ) -> bytes:
        attempts = MAX_GET_ATTEMPTS if method == "GET" else 1
        for attempt in range(attempts):
            logger.info("TeamStorm request %s /%s", method, path)
            try:
                async with self._get_session().request(
                    method, path, params=params, json=json, allow_redirects=False
                ) as response:
                    body = await response.read()
            except TimeoutError as exc:
                if method == "GET" and attempt + 1 < attempts:
                    await self._sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise TeamStormTimeoutError(
                    f"TeamStorm request timed out after {self._timeout:g} seconds."
                ) from exc
            except aiohttp.ClientError as exc:
                if method == "GET" and attempt + 1 < attempts:
                    await self._sleep(RETRY_BACKOFF_SECONDS[attempt])
                    continue
                raise TeamStormConnectionError("Could not connect to TeamStorm.") from exc

            if response.status in RETRYABLE_HTTP_STATUSES and attempt + 1 < attempts:
                await self._sleep(self._retry_delay(response, attempt))
                continue

            self._raise_for_status(response, resource=resource)
            return body

        raise AssertionError("TeamStorm request loop exited unexpectedly")

    @staticmethod
    def _retry_delay(response: aiohttp.ClientResponse, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, min(float(retry_after), MAX_RETRY_AFTER_SECONDS))
            except ValueError:
                pass
        return RETRY_BACKOFF_SECONDS[attempt]

    @staticmethod
    def _raise_for_status(response: aiohttp.ClientResponse, *, resource: str) -> None:
        status = response.status
        match status:
            case value if HTTPStatus.OK <= value < HTTPStatus.MULTIPLE_CHOICES:
                return
            case HTTPStatus.BAD_REQUEST:
                raise TeamStormBadRequestError(f"TeamStorm rejected the request for {resource}.")
            case HTTPStatus.UNAUTHORIZED:
                raise TeamStormAuthenticationError(
                    "TeamStorm authentication failed. Check TEAMSTORM_TOKEN."
                )
            case HTTPStatus.FORBIDDEN:
                raise TeamStormPermissionError(f"Access to TeamStorm {resource} is forbidden.")
            case HTTPStatus.NOT_FOUND:
                raise TeamStormNotFoundError(f"TeamStorm {resource} was not found.")
            case HTTPStatus.CONFLICT:
                raise TeamStormConflictError(f"TeamStorm reported a conflict for {resource}.")
            case HTTPStatus.TOO_MANY_REQUESTS:
                raise TeamStormRateLimitError("TeamStorm rate limit was exceeded.")
            case value if value >= HTTPStatus.INTERNAL_SERVER_ERROR:
                raise TeamStormServerError("TeamStorm returned a server error.")
            case _:
                raise TeamStormBadRequestError(
                    f"TeamStorm request for {resource} failed with HTTP {status}."
                )

    @staticmethod
    def _validate(
        model: type[ModelT],
        response: bytes,
        *,
        resource: str,
    ) -> ModelT:
        try:
            return TypeAdapter(model).validate_json(response)
        except ValidationError as exc:
            raise TeamStormInvalidResponseError(
                f"TeamStorm returned an invalid response for {resource}."
            ) from exc

    @staticmethod
    def _validate_list(
        adapter: TypeAdapter[list[ModelT]],
        response: bytes,
        *,
        resource: str,
    ) -> list[ModelT]:
        try:
            return adapter.validate_json(response)
        except ValidationError as exc:
            raise TeamStormInvalidResponseError(
                f"TeamStorm returned an invalid response for {resource}."
            ) from exc
