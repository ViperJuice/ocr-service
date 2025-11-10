"""Global error handling middleware."""
import logging
from typing import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Handle HTTP exceptions.

    Args:
        request: Request object
        exc: HTTP exception

    Returns:
        JSON error response
    """
    logger.warning(f"HTTP {exc.status_code}: {exc.detail} - {request.method} {request.url}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "code": f"HTTP_{exc.status_code}",
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request validation errors.

    Args:
        request: Request object
        exc: Validation error

    Returns:
        JSON error response
    """
    logger.warning(f"Validation error: {exc.errors()} - {request.method} {request.url}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "detail": exc.errors(),
            "code": "VALIDATION_ERROR",
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handle uncaught exceptions.

    Args:
        request: Request object
        exc: Exception

    Returns:
        JSON error response
    """
    logger.error(f"Unhandled exception: {exc} - {request.method} {request.url}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "code": "INTERNAL_ERROR",
        },
    )
