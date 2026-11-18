"""C4 adapters reusing the existing authentication and CSRF implementations."""

from fastapi import Depends, Header, Request

from app.api.dependencies import (
    AuthenticatedRequest, get_authenticated_request, get_request_settings, require_csrf,
)
from app.core.assistant_database import get_assistant_database


async def assistant_authenticated(request: Request, database=Depends(get_assistant_database)):
    def authenticate(db):
        result = get_authenticated_request(request, db, request.app.state.settings)
        db.commit()
        return result  # frozen identity/token only; no ORM/session crosses threads.
    return await database.run(authenticate, deadline=request.state.assistant_deadline)


def assistant_csrf(
    request: Request,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    authenticated: AuthenticatedRequest = Depends(assistant_authenticated),
    settings=Depends(get_request_settings),
):
    # Authorization captured here is never trusted for a later mutation: every
    # worker phase freshly revalidates the original session before taking locks.
    return require_csrf(request, csrf_token, authenticated, settings)
