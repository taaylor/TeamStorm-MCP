"""Parsing for human-readable TeamStorm task keys."""

from dataclasses import dataclass

from teamstorm_mcp.constants import TASK_KEY_PATTERN
from teamstorm_mcp.exceptions import InvalidTaskKeyError


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
