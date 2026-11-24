"""Structured error responses, request IDs, body limits and denied-access auditing."""

import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.core.errors import AppError, Forbidden, NotAuthenticated
from backend.core.logging import request_id_var

log = logging.getLogger("backend.api")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id_var.get(),
            "details": details,
        }
    }


def _audit_denied(request: Request, exc: AppError) -> None:
    container = getattr(request.app.state, "container", None)
    if container is None:
        return
    from backend.services import audit

    principal = getattr(request.state, "principal", None)
    mission = request.path_params.get("mission_id")
    try:
        from uuid import UUID

        mission_id = UUID(str(mission)) if mission else None
    except ValueError:
        mission_id = None
    try:
        with container.db.transaction() as session:
            audit.record(
                session,
                principal,
                "access.denied",
                resource_type="route",
                resource_id=request.url.path[:100],
                mission_id=mission_id,
                outcome="denied",
                details={"method": request.method, "code": exc.code},
            )
    except Exception:
        log.exception("could not audit denied request")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        if (
            isinstance(exc, (Forbidden, NotAuthenticated))
            or exc.status_code == 404
            and getattr(request.state, "principal", None)
        ):
            import asyncio

            await asyncio.to_thread(_audit_denied, request, exc)
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            body(exc.code, exc.message, exc.details), status_code=exc.status_code, headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(
            body("validation_error", "request validation failed", details), status_code=422
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return JSONResponse(body("internal_error", "internal server error"), status_code=500)


class RequestContextMiddleware:
    """Pure ASGI middleware: correlation ID, body-size limit and request metrics."""

    def __init__(self, app: ASGIApp, max_bytes: int, observe: Callable[[str, int, float], None]):
        self.app = app
        self.max_bytes = max_bytes
        self.observe = observe

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        supplied = headers.get("x-request-id", "")
        request_id = supplied if REQUEST_ID.match(supplied) else uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = {"code": 500}
        try:
            if scope["type"] == "http":
                length = headers.get("content-length")
                if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
                    await self._reject(send, 413, "payload_too_large", "request body too large")
                    status["code"] = 413
                    return
                received = 0

                async def limited_receive() -> Message:
                    nonlocal received
                    message = await receive()
                    if message["type"] == "http.request":
                        received += len(message.get("body", b""))
                        if received > self.max_bytes:
                            raise _BodyTooLarge
                    return message

                async def tracking_send(message: Message) -> None:
                    if message["type"] == "http.response.start":
                        status["code"] = message["status"]
                        message.setdefault("headers", [])
                        message["headers"] = [
                            *message["headers"],
                            (b"x-request-id", request_id.encode()),
                        ]
                    await send(message)

                try:
                    await self.app(scope, limited_receive, tracking_send)
                except _BodyTooLarge:
                    status["code"] = 413
                    await self._reject(send, 413, "payload_too_large", "request body too large")
            else:
                await self.app(scope, receive, send)
        finally:
            if scope["type"] == "http":
                route = scope.get("route")
                path = getattr(route, "path", None) or "unmatched"
                self.observe(
                    f"{scope.get('method', '')} {path}",
                    status["code"],
                    (time.perf_counter() - started) * 1000,
                )
            request_id_var.reset(token)

    @staticmethod
    async def _reject(send: Send, status: int, code: str, message: str) -> None:
        import json

        payload = json.dumps(body(code, message)).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": payload})


class _BodyTooLarge(Exception):
    pass


Handler = Callable[[Request], Awaitable[Any]]
