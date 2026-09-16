"""Application rules and defaults."""

import re
from typing import Final

DEFAULT_MAX_CONTEXT_ITEMS: Final[int] = 200
MAX_CONTEXT_ITEMS_LIMIT: Final[int] = 1_000

TASK_SUMMARY_HEADING: Final[str] = "Суть задачи"
WORK_DONE_HEADING: Final[str] = "Что было сделано"
WORK_DONE_PLACEHOLDER: Final[str] = "Работы ещё не описаны."

TASK_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<workspace>[A-Z][A-Z0-9]*)-(?P<number>[0-9]+)$",
    re.ASCII,
)
