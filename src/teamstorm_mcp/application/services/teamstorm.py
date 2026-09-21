"""Application services coordinating TeamStorm API operations."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from teamstorm_mcp.application.constants import (
    DEFAULT_MAX_CONTEXT_ITEMS,
    DEFAULT_PAGE_LINK_CONCURRENCY,
)
from teamstorm_mcp.application.exceptions import TeamStormBadRequestError, TeamStormError
from teamstorm_mcp.application.interfaces.teamstorm import TeamStormGateway
from teamstorm_mcp.application.models import (
    Attachment,
    Comment,
    Page,
    TaskContext,
    TaskPagesResult,
    TaskUpdate,
    WorkItem,
    WorkItemAttribute,
    WorkItemLink,
)
from teamstorm_mcp.application.parser import parse_task_key
from teamstorm_mcp.application.task_description import render_task_description
from teamstorm_mcp.application.workflow import Workflow


@dataclass(slots=True)
class SectionResult[T]:
    value: T | None = None
    error: TeamStormError | None = None


class TeamStormService:
    """Expose task-key-oriented operations independent of MCP."""

    def __init__(
        self,
        client: TeamStormGateway,
        *,
        max_context_items: int = DEFAULT_MAX_CONTEXT_ITEMS,
        workflow: Workflow | None = None,
        page_link_concurrency: int = DEFAULT_PAGE_LINK_CONCURRENCY,
    ) -> None:
        self._client = client
        self._max_context_items = max_context_items
        self.workflow = workflow
        self._page_link_concurrency = page_link_concurrency

    async def get_task(self, task_key: str) -> WorkItem:
        parsed = parse_task_key(task_key)
        return await self._client.get_workitem(parsed.workspace, parsed.key)

    async def get_comments(self, task_key: str) -> list[Comment]:
        parsed = parse_task_key(task_key)
        return await self._client.get_comments(parsed.workspace, parsed.key)

    async def add_comment(self, task_key: str, text: str) -> Comment:
        parsed = parse_task_key(task_key)
        return await self._client.add_comment(parsed.workspace, parsed.key, text)

    async def get_attachments(self, task_key: str) -> list[Attachment]:
        parsed = parse_task_key(task_key)
        return await self._client.get_attachments(parsed.workspace, parsed.key)

    async def get_links(self, task_key: str) -> list[WorkItemLink]:
        parsed = parse_task_key(task_key)
        return await self._client.get_links(parsed.workspace, parsed.key)

    async def get_task_pages(
        self,
        task_key: str,
        *,
        include_content: bool = True,
        max_items: int | None = None,
    ) -> TaskPagesResult:
        parsed = parse_task_key(task_key)
        limit = self._resolve_page_limit(max_items)
        await self._client.get_workitem(parsed.workspace, parsed.key)
        workspaces = await self._client.list_workspaces()
        candidates: list[tuple[str, Page]] = []
        warnings: list[str] = []

        for workspace in workspaces:
            try:
                documents = await self._client.list_documents(workspace.key)
            except TeamStormError as exc:
                warnings.append(f"Pages in workspace {workspace.key} could not be loaded. {exc}")
                continue
            candidates.extend((workspace.key, page) for page in documents)

        semaphore = asyncio.Semaphore(self._page_link_concurrency)

        async def find_page(candidate: tuple[str, Page]) -> tuple[Page | None, str | None]:
            workspace_key, page = candidate
            async with semaphore:
                try:
                    linked_tasks = await self._client.get_document_workitem_links(
                        workspace_key,
                        page.key,
                    )
                except TeamStormError as exc:
                    return None, f"Links for page {page.key} could not be loaded. {exc}"

            if not any(
                self._is_target_task(linked_task, parsed.workspace, parsed.key, workspace_key)
                for linked_task in linked_tasks
            ):
                return None, None

            linked_page = page.model_copy(update={"workspace_key": workspace_key})
            if not include_content:
                linked_page = linked_page.model_copy(update={"content": None})
            return linked_page, None

        matches = await asyncio.gather(*(find_page(candidate) for candidate in candidates))
        pages = [page for page, warning in matches if page is not None]
        warnings.extend(warning for _, warning in matches if warning is not None)
        return TaskPagesResult(
            task_key=parsed.key,
            pages=pages[:limit],
            warnings=warnings,
        )

    def _resolve_page_limit(self, max_items: int | None) -> int:
        if max_items is not None and max_items < 1:
            raise TeamStormBadRequestError("max_items must be greater than zero.")
        return min(max_items or self._max_context_items, self._max_context_items)

    @staticmethod
    def _is_target_task(
        linked_task: WorkItem,
        workspace: str,
        task_key: str,
        page_workspace: str,
    ) -> bool:
        if linked_task.key != task_key:
            return False
        linked_workspace = linked_task.workspace.key if linked_task.workspace else page_workspace
        return linked_workspace == workspace

    async def update_task(
        self,
        task_key: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> WorkItem:
        parsed = parse_task_key(task_key)
        if status is not None and self.workflow is not None:
            task = await self.get_task(task_key)
            if self.workflow.definition.resolve(task.status) == self.workflow.definition.resolve(
                status
            ):
                if name is None and description is None:
                    return task
                status = None
            else:
                await self.workflow.check(task.status, status, actor="mcp")
        return await self._client.update_workitem(
            parsed.workspace,
            parsed.key,
            TaskUpdate(name=name, description=description, status=status),
        )

    async def finalize_task(
        self, task_key: str, *, before_write: Callable[[], Awaitable[bool]]
    ) -> WorkItem:
        if self.workflow is None:
            raise RuntimeError("Finalization requires a workflow map")
        definition = self.workflow.definition
        target = definition.states[definition.scheduled_finalization.final_state].external_status
        task = await self.get_task(task_key)
        await self.workflow.check(task.status, target, actor="daemon")
        parsed = parse_task_key(task_key)
        if not await before_write():
            raise TeamStormBadRequestError("Closure schedule changed; finalization skipped")
        return await self._client.update_workitem(
            parsed.workspace, parsed.key, TaskUpdate(status=target)
        )

    async def list_tasks(self) -> list[WorkItem]:
        return await self._client.list_workitems()

    async def set_task_description(
        self,
        task_key: str,
        *,
        task_summary: str,
        work_done: list[str] | None = None,
    ) -> WorkItem:
        description = render_task_description(task_summary, work_done)
        return await self.update_task(task_key, description=description)

    async def get_task_context(
        self,
        task_key: str,
        *,
        include_comments: bool = True,
        include_attributes: bool = True,
        include_attachments: bool = True,
        include_links: bool = True,
        include_children: bool = False,
    ) -> TaskContext:
        parsed = parse_task_key(task_key)
        task = await self._client.get_workitem(parsed.workspace, parsed.key)

        (
            attributes_result,
            comments_result,
            attachments_result,
            links_result,
            children_result,
        ) = await self._load_sections(
            parsed.workspace,
            parsed.key,
            include_attributes=include_attributes,
            include_comments=include_comments,
            include_attachments=include_attachments,
            include_links=include_links,
            include_children=include_children,
        )

        warnings: list[str] = []
        attributes = self._required_section(
            attributes_result,
            fallback=task.attributes,
            warning="Could not load the dedicated attributes endpoint; using task attributes.",
            warnings=warnings,
        )
        comments = self._required_section(comments_result)
        attachments = self._optional_section(
            attachments_result,
            "Attachments could not be loaded.",
            warnings,
        )
        links = self._optional_section(links_result, "Related tasks could not be loaded.", warnings)
        children = self._optional_section(
            children_result,
            "Child tasks could not be loaded.",
            warnings,
        )

        attributes = self._limit(attributes, "attributes", warnings)
        comments = self._limit(comments, "comments", warnings)
        attachments = self._limit(attachments, "attachments", warnings)
        links = self._limit(links, "related tasks", warnings)
        children = self._limit(children, "child tasks", warnings)

        return TaskContext(
            key=parsed.key,
            workspace=parsed.workspace,
            task=task,
            attributes=attributes,
            comments=comments,
            attachments=attachments,
            links=links,
            children=children,
            warnings=warnings,
        )

    async def _load_sections(
        self,
        workspace: str,
        task_key: str,
        *,
        include_attributes: bool,
        include_comments: bool,
        include_attachments: bool,
        include_links: bool,
        include_children: bool,
    ) -> tuple[
        SectionResult[list[WorkItemAttribute]],
        SectionResult[list[Comment]],
        SectionResult[list[Attachment]],
        SectionResult[list[WorkItemLink]],
        SectionResult[list[WorkItem]],
    ]:
        return await asyncio.gather(
            self._load(self._client.get_workitem_attributes(workspace, task_key))
            if include_attributes
            else self._ready([]),
            self._load(self._client.get_comments(workspace, task_key))
            if include_comments
            else self._ready([]),
            self._load(self._client.get_attachments(workspace, task_key))
            if include_attachments
            else self._ready([]),
            self._load(self._client.get_links(workspace, task_key))
            if include_links
            else self._ready([]),
            self._load(self._client.get_children(workspace, task_key))
            if include_children
            else self._ready([]),
        )

    @staticmethod
    async def _load[T](awaitable: Awaitable[T]) -> SectionResult[T]:
        try:
            return SectionResult(value=await awaitable)
        except TeamStormError as exc:
            return SectionResult(error=exc)

    @staticmethod
    async def _ready[T](value: T) -> SectionResult[T]:
        return SectionResult(value=value)

    @staticmethod
    def _required_section[T](
        result: SectionResult[T],
        *,
        fallback: T | None = None,
        warning: str | None = None,
        warnings: list[str] | None = None,
    ) -> T:
        if result.error is None and result.value is not None:
            return result.value
        if fallback is not None:
            if warning is not None and warnings is not None:
                warnings.append(warning)
            return fallback
        if result.error is not None:
            raise result.error
        raise RuntimeError("Required TeamStorm context section has no value")

    @staticmethod
    def _optional_section[T](
        result: SectionResult[list[T]],
        warning: str,
        warnings: list[str],
    ) -> list[T]:
        if result.error is not None:
            warnings.append(f"{warning} {result.error}")
            return []
        return result.value or []

    def _limit[T](self, items: list[T], section: str, warnings: list[str]) -> list[T]:
        if len(items) <= self._max_context_items:
            return items
        warnings.append(
            f"The {section} section was truncated from {len(items)} to "
            f"{self._max_context_items} items."
        )
        return items[-self._max_context_items :]
