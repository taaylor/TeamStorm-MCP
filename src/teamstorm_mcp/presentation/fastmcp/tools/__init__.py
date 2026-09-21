from fastmcp import FastMCP

from teamstorm_mcp.presentation.fastmcp.tools.attachments import register_attachments_tools
from teamstorm_mcp.presentation.fastmcp.tools.comments import register_comments_tools
from teamstorm_mcp.presentation.fastmcp.tools.links import register_links_tools
from teamstorm_mcp.presentation.fastmcp.tools.pages import register_pages_tools
from teamstorm_mcp.presentation.fastmcp.tools.scheduling import register_scheduling_tools
from teamstorm_mcp.presentation.fastmcp.tools.workitems import register_workitems_tools

__all__ = ["register_tools"]


def register_tools(mcp: FastMCP) -> None:
    """Register the public TeamStorm MCP tools."""
    register_workitems_tools(mcp)
    register_comments_tools(mcp)
    register_attachments_tools(mcp)
    register_links_tools(mcp)
    register_pages_tools(mcp)
    register_scheduling_tools(mcp)
