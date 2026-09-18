"""Errores de API con código estable, según la Especificación de API v1.1 (sección 4)."""
from fastapi import HTTPException


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, detail: dict | None = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "detail": detail})
        self.code = code


def err(status_code: int, code: str, message: str, detail: dict | None = None) -> ApiError:
    return ApiError(status_code, code, message, detail)


# Helpers de los errores comunes
def not_found(what: str = "El recurso indicado no existe.", code: str = "NOT_FOUND") -> ApiError:
    return err(404, code, what)


def forbidden(code: str = "FORBIDDEN_ROLE", message: str = "El rol del token no tiene acceso a este recurso.") -> ApiError:
    return err(403, code, message)


def conflict(code: str, message: str, detail: dict | None = None) -> ApiError:
    return err(409, code, message, detail)


def unauthorized(code: str, message: str) -> ApiError:
    return err(401, code, message)


def unprocessable(code: str, message: str, detail: dict | None = None) -> ApiError:
    return err(422, code, message, detail)
