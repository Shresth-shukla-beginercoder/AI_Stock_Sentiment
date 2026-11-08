"""One error envelope for the whole API (CLAUDE.md: single error envelope).

Error responses: {"success": false, "error": {"code","message","details"?}, "data_mode", "as_of"}
Never exposes internal exception traces; 500 bodies are generic.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.schemas.envelope import APIError, as_of_now

__all__ = ["error_body", "install_exception_handlers"]


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    settings = get_settings()
    body: dict = {
        "success": False,
        "error": {"code": code, "message": message},
        "data_mode": settings.data_mode,
        "as_of": as_of_now(),
    }
    if details is not None:
        body["error"]["details"] = details
    return body


_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
    503: "service_unavailable",
}


async def _api_error(request: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            "validation_error",
            "Request validation failed.",
            {"errors": exc.errors()},
        ),
    )


async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _CODE_BY_STATUS.get(exc.status_code, "error")
    return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Log server-side with trace; client gets a generic body (no trace exposure).
    import logging

    logging.getLogger("app.api.errors").exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=error_body("internal_error", "Unexpected server error."))


def install_exception_handlers(app) -> None:
    app.add_exception_handler(APIError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(Exception, _unhandled)
