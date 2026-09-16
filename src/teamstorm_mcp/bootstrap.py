from collections.abc import AsyncIterator
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from teamstorm_mcp.adapters.config import Settings
from teamstorm_mcp.adapters.sqlite_closures import SQLiteClosureRepository
from teamstorm_mcp.adapters.teamstorm.client import TeamStormClient
from teamstorm_mcp.application.scheduling import ClosureService
from teamstorm_mcp.application.services.teamstorm import TeamStormService
from teamstorm_mcp.constants import PACKAGE_VERSION
from teamstorm_mcp.presentation.fastmcp.constants import SERVER_INSTRUCTIONS, SERVER_NAME
from teamstorm_mcp.presentation.fastmcp.tools import register_tools


@lifespan
async def application_lifespan(
    server: FastMCP,
) -> AsyncIterator[dict[str, Any] | None]:
    del server
    settings = Settings()  # type: ignore[call-arg]  # Values come from the environment.
    repository = SQLiteClosureRepository(settings.teamstorm_queue_path.expanduser())
    await repository.initialize()
    async with TeamStormClient(
        base_url=str(settings.teamstorm_url),
        token=settings.teamstorm_token,
        timeout=settings.teamstorm_timeout,
    ) as client:
        service = TeamStormService(client, max_context_items=settings.teamstorm_max_context_items)
        context: dict[str, Any] = {
            "service": service,
            "closures": ClosureService(repository, service),
        }
        yield context


mcp = FastMCP(
    name=SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
    version=PACKAGE_VERSION,
    lifespan=application_lifespan,
    mask_error_details=True,
    strict_input_validation=True,
)


register_tools(mcp)


def main() -> None:
    """Run TeamStorm MCP using STDIO."""
    mcp.run(transport="stdio", show_banner=False)
