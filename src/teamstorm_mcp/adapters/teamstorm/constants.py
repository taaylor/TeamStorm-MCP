"""TeamStorm HTTP transport defaults."""

from http import HTTPStatus
from typing import Final

TEAMSTORM_API_PATH: Final[str] = "/cwm/public/api/v1"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
MAX_TIMEOUT_SECONDS: Final[float] = 300.0

MAX_GET_ATTEMPTS: Final[int] = 3
RETRYABLE_HTTP_STATUSES: Final[frozenset[HTTPStatus]] = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)
RETRY_BACKOFF_SECONDS: Final[tuple[float, ...]] = (0.5, 1.0, 2.0)
MAX_RETRY_AFTER_SECONDS: Final[float] = 30.0

PAGINATION_PAGE_SIZE: Final[int] = 200
MAX_PAGINATED_ITEMS: Final[int] = 1_000
