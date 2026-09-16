"""Response envelopes specific to the TeamStorm REST API."""

from pydantic import Field

from teamstorm_mcp.application.models import TeamStormModel


class ItemsResponse[T](TeamStormModel):
    """TeamStorm envelope used by several list endpoints."""

    items: list[T] = Field(default_factory=list)


class PaginationResponse[T](ItemsResponse[T]):
    """Token-based TeamStorm pagination envelope."""

    from_token: str | None = None
    max_items_count: int | None = None
    next_token: str | None = None
