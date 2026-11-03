"""HTTP security middleware for the local-first API.

- Origin allowlist (dev server + same origin).
- Optional bearer token via AGENT_API_TOKEN (preflight requests are exempt).
- Without a token, only loopback clients and loopback Host headers are accepted;
  the Host check blocks DNS rebinding against an unauthenticated local server.
"""

import hmac
import os
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

DEV_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
LOOPBACK_CLIENTS = ("127.0.0.1", "::1", "localhost", "testclient")
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "testserver")

CallNext = Callable[[Request], Awaitable[Response]]


def _deny(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


def check_request(request: Request) -> JSONResponse | None:
    """Return an error response when the request must be rejected, else None."""
    origin = request.headers.get("origin")
    allowed = {*DEV_ORIGINS, str(request.base_url).rstrip("/")}
    if origin and origin not in allowed:
        return _deny(403, "origin_forbidden", "Origin not allowed")
    token = os.getenv("AGENT_API_TOKEN", "")
    if token:
        if request.method == "OPTIONS":
            return None
        expected = "Bearer " + token
        if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
            return _deny(401, "unauthorized", "API token required")
        return None
    if request.client and request.client.host not in LOOPBACK_CLIENTS:
        return _deny(403, "token_required", "Remote access requires AGENT_API_TOKEN")
    if request.url.hostname not in LOOPBACK_HOSTS:
        return _deny(403, "host_forbidden", "Loopback host required")
    return None


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def security(request: Request, call_next: CallNext) -> Response:
        if request.url.path.startswith("/api/"):
            denied = check_request(request)
            if denied is not None:
                return denied
        return await call_next(request)
