"""NovaForge SDK exceptions."""


class NovaForgeError(Exception):
    """Base exception for all NovaForge SDK errors."""


class AuthenticationError(NovaForgeError):
    """Invalid or missing authentication credentials."""


class NotFoundError(NovaForgeError):
    """Requested resource was not found."""


class RateLimitError(NovaForgeError):
    """API rate limit exceeded."""


class ValidationError(NovaForgeError):
    """Request validation failed."""


class ServerError(NovaForgeError):
    """Server-side error occurred."""


class ConnectionError(NovaForgeError):
    """Failed to connect to the NovaForge API."""
