class NovaForgeError(Exception):
    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None, details: dict | None = None) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class NotFoundError(NovaForgeError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, resource: str = "Resource", identifier: str = "") -> None:
        msg = f"{resource} not found" + (f": {identifier}" if identifier else "")
        super().__init__(message=msg)


class ValidationError(NovaForgeError):
    status_code = 422
    code = "VALIDATION_ERROR"


class AuthenticationError(NovaForgeError):
    status_code = 401
    code = "UNAUTHORIZED"


class AuthorizationError(NovaForgeError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(NovaForgeError):
    status_code = 409
    code = "CONFLICT"


class ServiceUnavailableError(NovaForgeError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"
