"""Uniform HTTP error format: ``{"error": {"code": "...", "message": "..."}}``.

FastAPI request validation errors keep the standard 422 ``detail`` array.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse


def not_found(message: str = "Resource not found") -> HTTPException:
    return HTTPException(404, message)


def install(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "http_" + str(exc.status_code), "message": str(exc.detail)}},
            status_code=exc.status_code,
        )
