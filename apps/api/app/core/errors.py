from fastapi import HTTPException


class DomainError(HTTPException):
    """Business rule violation (deterministic). Returned as 409 with a machine-readable code."""

    def __init__(self, code: str, message: str, status_code: int = 409, details: dict | None = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details or {}})


def not_found(entity: str) -> HTTPException:
    # Same response for "missing" and "other tenant" to avoid cross-tenant enumeration.
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"{entity} not found"})
