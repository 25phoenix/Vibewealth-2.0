"""Phase 9C.3/9C.4 assistant APIs; production generation remains disabled."""

import re
import time

import anyio
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.assistant_http import AssistantRoute
from app.api.dependencies import AuthenticatedRequest, get_authenticated_request, require_csrf
from app.core.database import get_db
from app.core.assistant_database import get_assistant_database
from app.api.assistant_dependencies import assistant_authenticated, assistant_csrf
from app.schemas.assistant import (
    MAX_REQUEST_BYTES, WORK_DEADLINE_SECONDS, ConversationCreateRequest,
    HTTP_ERROR_STATUS, ConversationDto, ConversationPageDto, ErrorDto, HttpErrorCode, MessagePageDto,
    PaginationRequest, canonical_uuid,
    MessageSubmitRequest, AttemptRequest, TurnDto,
)
from app.services import assistant_conversations as service
from app.services import assistant_turns as turns
from app.services.assistant_contracts import ContractViolation, parse_request_body, parse_idempotency_header
from app.services.authentication import get_current_user

router = APIRouter(
    prefix="/api/assistant", tags=["assistant"], route_class=AssistantRoute,
    responses={code: {"model": ErrorDto} for code in set(HTTP_ERROR_STATUS.values())},
)
reads = APIRouter(route_class=AssistantRoute, dependencies=[Depends(get_authenticated_request)])


def _query(request, *, paginated=False):
    values = {}
    for key, value in request.query_params.multi_items():
        if not paginated or key not in {"offset", "limit"} or key in values:
            raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
        if not re.fullmatch(r"[0-9]+", value):
            raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
        try:
            values[key] = int(value)
        except ValueError:
            raise ContractViolation(HttpErrorCode.INVALID_REQUEST) from None
    try:
        return PaginationRequest.model_validate(values)
    except ValueError:
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST) from None


def _conversation_id(value):
    try:
        return canonical_uuid(value)
    except ValueError:
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST) from None


async def _body(request: Request, *, empty=False, schema=ConversationCreateRequest):
    encodings = request.headers.getlist("content-encoding")
    if len(encodings) > 1:
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
    body = bytearray()
    with anyio.fail_after(max(0, request.state.assistant_deadline - time.monotonic())):
        async for chunk in request.stream():
            if empty and chunk:
                raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                raise ContractViolation(HttpErrorCode.REQUEST_TOO_LARGE)
            body.extend(chunk)
    if empty:
        if encodings and encodings[0].lower() != "identity":
            raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
        return None
    return parse_request_body([bytes(body)], schema,
                              content_encoding=encodings[0] if encodings else None)


async def _write_body(request: Request):
    """Finish client-controlled I/O before any session or connection dependency.

    The same dependency is cached for the POST payload. Authentication/CSRF
    follow this dependency, so no previously captured permission is reused.
    """
    path = request.url.path.rstrip("/")
    schema = (MessageSubmitRequest if path.endswith("/messages") else
              AttemptRequest if path.endswith(("/retry", "/abandon")) else ConversationCreateRequest)
    return await _body(request, empty=request.method == "DELETE", schema=schema)


writes = APIRouter(
    route_class=AssistantRoute,
    dependencies=[Depends(_write_body), Depends(require_csrf)],
)
c4_writes = APIRouter(route_class=AssistantRoute,
                     dependencies=[Depends(_write_body), Depends(assistant_csrf)])
c4_reads = APIRouter(route_class=AssistantRoute)


def _admit(request, authenticated, *, write=False):
    retry_after = request.app.state.assistant_rate_limiter.check(
        authenticated.current_user.user_id, write=write,
    )
    if retry_after is not None:
        error = ContractViolation(HttpErrorCode.RATE_LIMITED)
        error.retry_after = retry_after
        raise error


def _reauthenticate(db, authenticated):
    current = get_current_user(db, session_token=authenticated.session_token)
    original = authenticated.current_user
    if current is None or (current.user_id, current.session_id) != (original.user_id, original.session_id):
        raise ContractViolation(HttpErrorCode.AUTHENTICATION_REQUIRED)


def _read_snapshot(db, operation):
    # Commit the dependency's session-activity UPDATE before opening a separate
    # consistent read snapshot. No auth-row lock is held during these reads.
    db.commit()
    db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    db.execute(text("SET TRANSACTION READ ONLY"))
    result = operation()
    db.commit()
    return result


@writes.post("/conversations", response_model=ConversationDto, status_code=201)
def create_conversation(
    request: Request, response: Response,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    payload: ConversationCreateRequest = Depends(_write_body),
    db: Session = Depends(get_db),
):
    _query(request)
    _admit(request, authenticated, write=True)
    user_id = authenticated.current_user.user_id
    try:
        conversation, created = service.create_conversation(db, user_id=user_id, payload=payload)
        result = service.conversation_dtos(db, user_id=user_id, conversations=[conversation])[0]
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if not service.is_creation_primary_key_conflict(error):
            raise ContractViolation(HttpErrorCode.INTERNAL_ERROR) from None
        # Failed transaction and its row locks are gone; start with fresh session
        # validation before inspecting the UUID winner. Never retry the INSERT.
        _reauthenticate(db, authenticated)
        conversation = service.resolve_creation(db, user_id=user_id, payload=payload)
        result = service.conversation_dtos(db, user_id=user_id, conversations=[conversation])[0]
        db.commit()
        created = False
    response.status_code = 201 if created else 200
    return result


@reads.get("/conversations", response_model=ConversationPageDto)
def list_conversations(
    request: Request, authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
):
    pagination = _query(request, paginated=True)
    _admit(request, authenticated)
    return _read_snapshot(db, lambda: service.list_conversations(
        db, user_id=authenticated.current_user.user_id, pagination=pagination,
    ))


@reads.get("/conversations/{conversation_id}", response_model=ConversationDto)
def get_conversation(
    conversation_id: str, request: Request,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
):
    _query(request)
    identifier = _conversation_id(conversation_id)
    _admit(request, authenticated)
    return _read_snapshot(db, lambda: service.get_conversation(
        db, user_id=authenticated.current_user.user_id, conversation_id=identifier,
    ))


@reads.get("/conversations/{conversation_id}/messages", response_model=MessagePageDto)
def list_messages(
    conversation_id: str, request: Request,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
):
    pagination = _query(request, paginated=True)
    identifier = _conversation_id(conversation_id)
    _admit(request, authenticated)
    return _read_snapshot(db, lambda: service.list_messages(
        db, user_id=authenticated.current_user.user_id, conversation_id=identifier, pagination=pagination,
    ))


@writes.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, request: Request,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    db: Session = Depends(get_db),
):
    _query(request)
    identifier = _conversation_id(conversation_id)
    _admit(request, authenticated, write=True)
    service.delete_conversation(db, user_id=authenticated.current_user.user_id, conversation_id=identifier)
    db.commit()
    return Response(status_code=204)


def _turn_response(response, result):
    dto, status = result
    response.status_code = status
    if status == 202:
        response.headers["Retry-After"] = "2"
    return dto


@c4_writes.post("/conversations/{conversation_id}/messages", response_model=TurnDto, status_code=201)
async def submit_message(
    conversation_id: str, request: Request, response: Response,
    payload: MessageSubmitRequest = Depends(_write_body),
    authenticated: AuthenticatedRequest = Depends(assistant_authenticated),
    database=Depends(get_assistant_database), executor=Depends(turns.get_test_executor),
):
    _query(request)
    identifier = _conversation_id(conversation_id)
    key = parse_idempotency_header(request.scope["headers"])
    _admit(request, authenticated)  # Read/abuse budget; never generation quota for replay.
    return _turn_response(response, await turns.generate(
        database, authenticated, identifier, key=key, content=payload.content,
        admission=request.app.state.assistant_admission, executor=executor,
        test_environment=request.app.state.settings.app_environment == "test",
        deadline=request.state.assistant_deadline,
        receive=request.receive,
    ))


@c4_reads.get("/turns/by-key", response_model=TurnDto)
async def lookup_turn(
    request: Request, authenticated: AuthenticatedRequest = Depends(assistant_authenticated),
    database=Depends(get_assistant_database),
):
    _query(request)
    key = parse_idempotency_header(request.scope["headers"])
    _admit(request, authenticated)
    return await database.run(lambda db: _read_snapshot(db, lambda: turns.lookup(
        db, authenticated.current_user.user_id, key)), deadline=request.state.assistant_deadline)


@c4_reads.get("/conversations/{conversation_id}/turns/{turn_id}", response_model=TurnDto)
async def get_turn(
    conversation_id: str, turn_id: str, request: Request,
    authenticated: AuthenticatedRequest = Depends(assistant_authenticated), database=Depends(get_assistant_database),
):
    _query(request)
    identifier, turn_identifier = _conversation_id(conversation_id), _conversation_id(turn_id)
    _admit(request, authenticated)
    return await database.run(lambda db: _read_snapshot(db, lambda: turns.get_turn(
        db, authenticated.current_user.user_id, identifier, turn_identifier)), deadline=request.state.assistant_deadline)


@c4_writes.post("/conversations/{conversation_id}/turns/{turn_id}/retry", response_model=TurnDto)
async def retry_turn(
    conversation_id: str, turn_id: str, request: Request, response: Response,
    payload: AttemptRequest = Depends(_write_body),
    authenticated: AuthenticatedRequest = Depends(assistant_authenticated),
    database=Depends(get_assistant_database), executor=Depends(turns.get_test_executor),
):
    _query(request)
    identifier, turn_identifier = _conversation_id(conversation_id), _conversation_id(turn_id)
    _admit(request, authenticated)
    return _turn_response(response, await turns.generate(
        database, authenticated, identifier, turn_id=turn_identifier, expected=payload.expected_attempt_no,
        admission=request.app.state.assistant_admission, executor=executor,
        test_environment=request.app.state.settings.app_environment == "test",
        deadline=request.state.assistant_deadline,
        receive=request.receive,
    ))


@c4_writes.post("/conversations/{conversation_id}/turns/{turn_id}/abandon", response_model=TurnDto)
async def abandon_turn(
    conversation_id: str, turn_id: str, request: Request,
    payload: AttemptRequest = Depends(_write_body),
    authenticated: AuthenticatedRequest = Depends(assistant_authenticated), database=Depends(get_assistant_database),
):
    _query(request)
    identifier, turn_identifier = _conversation_id(conversation_id), _conversation_id(turn_id)
    _admit(request, authenticated, write=True)
    def abandon(db):
        turns.reauthenticate(db, authenticated)
        return turns.abandon(db, authenticated, identifier, turn_identifier, payload.expected_attempt_no)
    return await database.run(abandon, deadline=request.state.assistant_deadline)


router.include_router(reads)
router.include_router(writes)
router.include_router(c4_reads)
router.include_router(c4_writes)
