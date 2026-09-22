"""TeamStorm operations required by the application layer."""

from typing import Protocol

from teamstorm_mcp.application.models import (
    Attachment,
    Comment,
    Page,
    TaskUpdate,
    WorkItem,
    WorkItemAttribute,
    WorkItemLink,
    WorkspaceReference,
)


class TeamStormGateway(Protocol):
    async def list_workitems(self) -> list[WorkItem]: ...

    async def list_workspaces(self) -> list[WorkspaceReference]: ...

    async def list_documents(self, workspace: str) -> list[Page]: ...

    async def get_workitem(self, workspace: str, workitem: str) -> WorkItem: ...

    async def get_workitem_attributes(
        self,
        workspace: str,
        workitem: str,
    ) -> list[WorkItemAttribute]: ...

    async def get_comments(self, workspace: str, workitem: str) -> list[Comment]: ...

    async def add_comment(self, workspace: str, workitem: str, text: str) -> Comment: ...

    async def get_attachments(self, workspace: str, workitem: str) -> list[Attachment]: ...

    async def get_links(self, workspace: str, workitem: str) -> list[WorkItemLink]: ...

    async def get_document_workitem_links(
        self,
        workspace: str,
        document: str,
    ) -> list[WorkItem]: ...

    async def get_children(self, workspace: str, workitem: str) -> list[WorkItem]: ...

    async def update_workitem(
        self,
        workspace: str,
        workitem: str,
        update: TaskUpdate,
    ) -> WorkItem: ...
