"""Parsing for human-readable TeamStorm task keys."""

import re
from dataclasses import dataclass

from teamstorm_mcp.application.constants import TASK_KEY_PATTERN
from teamstorm_mcp.application.exceptions import InvalidTaskKeyError, TeamStormBadRequestError


def parse_workspace_key(value: str) -> str:
    """Normalize a workspace key before using it in an API path."""
    normalized = value.strip().upper()
    if re.fullmatch(r"[A-Z][A-Z0-9]*", normalized, re.ASCII) is None:
        raise TeamStormBadRequestError("Invalid TeamStorm workspace key. Expected a value like TS.")
    return normalized


@dataclass(frozen=True, slots=True)
class TaskKey:
    """Normalized TeamStorm task key and its workspace component."""

    workspace: str
    key: str


def parse_task_key(value: str) -> TaskKey:
    """Normalize and validate a human-readable TeamStorm task key."""

    normalized = value.strip().upper()
    match = TASK_KEY_PATTERN.fullmatch(normalized)
    if match is None:
        raise InvalidTaskKeyError(
            f"Invalid TeamStorm task key {value!r}. Expected a value like TS-123."
        )
    return TaskKey(workspace=match.group("workspace"), key=normalized)
