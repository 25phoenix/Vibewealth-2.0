"""Assistant-scoped sanitized error mapping and no-store response boundary."""

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import OperationalError
from starlette.datastructures import MutableHeaders
import time
import anyio

from app.schemas.assistant import HTTP_ERROR_MESSAGES, HTTP_ERROR_STATUS, ErrorDto, HttpErrorCode
from app.services.assistant_contracts import ContractViolation
from app.schemas.assistant import WORK_DEADLINE_SECONDS


def error_response(code, *, retry_after=None, current_turn=None):
    payload = ErrorDto(code=code, detail=HTTP_ERROR_MESSAGES[code], issues=[], current_turn=current_turn)
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(payload.model_dump(mode="json"), status_code=HTTP_ERROR_STATUS[code], headers=headers)


class AssistantRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            request.scope["assistant_route_matched"] = True
            request.state.assistant_deadline = time.monotonic() + WORK_DEADLINE_SECONDS
            try:
                with anyio.fail_after(max(0, request.state.assistant_deadline - time.monotonic())):
                    return await original(request)
            except ContractViolation as error:
                return error_response(error.code, retry_after=getattr(error, "retry_after", None),
                                      current_turn=getattr(error, "current_turn", None))
            except HTTPException as error:
                if error.status_code == 401:
                    code = HttpErrorCode.AUTHENTICATION_REQUIRED
                elif error.status_code == 403 and error.detail == "Request origin is not allowed":
                    code = HttpErrorCode.ORIGIN_REJECTED
                elif error.status_code == 403:
                    code = HttpErrorCode.CSRF_FAILED
                else:
                    code = HttpErrorCode.INVALID_REQUEST
                return error_response(code)
            except RequestValidationError:
                return error_response(HttpErrorCode.INVALID_REQUEST)
            except OperationalError:
                return error_response(HttpErrorCode.DATABASE_UNAVAILABLE)
            except TimeoutError:
                return error_response(HttpErrorCode.WORK_DEADLINE_EXCEEDED)
            except Exception:
                # Do not serialize exception text, SQL parameters or validation input.
                return error_response(HttpErrorCode.INTERNAL_ERROR)

        return handler


class AssistantNoStoreMiddleware:
    """Include framework/CORS errors and preflight responses, not just handlers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/api/assistant" or path.startswith("/api/assistant/")):
            return await self.app(scope, receive, send)

        started = False
        replacement = None
        replacement_sent = False

        async def no_store(message):
            nonlocal started, replacement, replacement_sent
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                if not scope.get("assistant_route_matched") and message["status"] in {404, 405}:
                    code = (HttpErrorCode.ASSISTANT_ROUTE_NOT_FOUND if message["status"] == 404
                            else HttpErrorCode.METHOD_NOT_ALLOWED)
                    replacement = error_response(code).body
                    # Retain Allow and CORS headers from the framework response,
                    # replacing only its representation metadata and body.
                    headers["Content-Type"] = "application/json"
                    headers["Content-Length"] = str(len(replacement))
            elif message["type"] == "http.response.body" and replacement is not None:
                if not replacement_sent:
                    replacement_sent = True
                    await send({"type": "http.response.body", "body": replacement, "more_body": False})
                return
            await send(message)

        try:
            await self.app(scope, receive, no_store)
        except Exception:
            if started:
                raise
            # Include failures outside APIRoute (for example dependency cleanup)
            # without handing raw diagnostics to the outer server-error handler.
            await error_response(HttpErrorCode.INTERNAL_ERROR)(scope, receive, no_store)
