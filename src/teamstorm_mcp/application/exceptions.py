"""Domain exceptions exposed by the TeamStorm integration layer."""


class TeamStormError(Exception):
    """Base exception for expected TeamStorm integration failures."""


class InvalidTaskKeyError(TeamStormError):
    """Raised when a human-readable TeamStorm task key is invalid."""


class TeamStormBadRequestError(TeamStormError):
    """Raised when TeamStorm rejects request parameters or body data."""


class TeamStormAuthenticationError(TeamStormError):
    """Raised when TEAMSTORM_TOKEN is invalid or missing privileges."""


class TeamStormPermissionError(TeamStormError):
    """Raised when the authenticated user cannot access an object."""


class TeamStormNotFoundError(TeamStormError):
    """Raised when a requested TeamStorm object does not exist."""


class TeamStormConflictError(TeamStormError):
    """Raised when a TeamStorm write conflicts with current state."""


class TeamStormRateLimitError(TeamStormError):
    """Raised when TeamStorm keeps rate limiting a request."""


class TeamStormServerError(TeamStormError):
    """Raised when TeamStorm returns a server-side failure."""


class TeamStormTimeoutError(TeamStormError):
    """Raised when a TeamStorm request exceeds its configured timeout."""


class TeamStormConnectionError(TeamStormError):
    """Raised when TeamStorm cannot be reached."""


class TeamStormInvalidResponseError(TeamStormError):
    """Raised when TeamStorm returns data that cannot be validated."""
