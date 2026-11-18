"""Phase 9C.1 assistant contracts; no routes, persistence or provider adapters."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

MAX_CONTENT_SCALARS = 4_000
MAX_REQUEST_BYTES = 65_536
MAX_PROVIDER_BYTES = 4_096
MAX_ATTEMPTS = 3
MAX_CLAIMS = 64
MAX_SELECTED_CLAIMS = 12
MAX_CONTEXT_TOKENS = 16_384
MAX_OUTPUT_TOKENS = 512
MAX_HISTORY_PAIRS = 6
MAX_ACCOUNT_DETAILS = 10
MAX_BUDGET_DETAILS = 10
MAX_GOAL_DETAILS = 10
MAX_RECENT_TRANSACTIONS = 10
MAX_CATEGORY_TOTALS = 5
MAX_CATEGORY_INCREASES = 5
MAX_CONVERSATIONS = 100
MAX_TURNS_PER_CONVERSATION = 1_000
GLOBAL_PROVIDER_CAPACITY = 2
USER_PROVIDER_CAPACITY = 1
GENERATION_STARTS_PER_MINUTE = 8
READS_PER_MINUTE = 120
WRITES_PER_MINUTE = 30
MAX_LIMITER_BUCKETS = 4_096
POLL_SECONDS = 2
CONTEXT_DEADLINE_SECONDS = 5
LOCK_DEADLINE_SECONDS = 2
CONNECT_DEADLINE_SECONDS = 2
PROVIDER_DEADLINE_SECONDS = 45
WORK_DEADLINE_SECONDS = 60
LEASE_SECONDS = 90
IDEMPOTENCY_HEADER = "Idempotency-Key"


class TurnStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class PersistedFailureCode(StrEnum):
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    INVALID_PROVIDER_RESPONSE = "INVALID_PROVIDER_RESPONSE"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    SESSION_INVALIDATED = "SESSION_INVALIDATED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"
    CONTEXT_LIMIT = "CONTEXT_LIMIT"
    FINANCIAL_INVARIANT = "FINANCIAL_INVARIANT"
    OUTPUT_REJECTED = "OUTPUT_REJECTED"


class TurnResponseErrorCode(StrEnum):
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    INVALID_PROVIDER_RESPONSE = "INVALID_PROVIDER_RESPONSE"
    CONTEXT_UNAVAILABLE = "CONTEXT_UNAVAILABLE"
    SESSION_INVALIDATED = "SESSION_INVALIDATED"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"
    CONTEXT_LIMIT = "CONTEXT_LIMIT"
    FINANCIAL_INVARIANT = "FINANCIAL_INVARIANT"
    OUTPUT_REJECTED = "OUTPUT_REJECTED"
    GENERATION_INTERRUPTED = "GENERATION_INTERRUPTED"


RETRYABLE_FAILURES = frozenset({
    PersistedFailureCode.PROVIDER_TIMEOUT,
    PersistedFailureCode.PROVIDER_UNAVAILABLE,
    PersistedFailureCode.PROVIDER_RATE_LIMITED,
    PersistedFailureCode.INVALID_PROVIDER_RESPONSE,
    PersistedFailureCode.CONTEXT_UNAVAILABLE,
    PersistedFailureCode.SESSION_INVALIDATED,
    PersistedFailureCode.INTERNAL_FAILURE,
})


class HttpErrorCode(StrEnum):
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    ORIGIN_REJECTED = "ORIGIN_REJECTED"
    CSRF_FAILED = "CSRF_FAILED"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    TURN_NOT_FOUND = "TURN_NOT_FOUND"
    ASSISTANT_ROUTE_NOT_FOUND = "ASSISTANT_ROUTE_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    CONVERSATION_CREATE_CONFLICT = "CONVERSATION_CREATE_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    UNRESOLVED_TURN = "UNRESOLVED_TURN"
    ATTEMPT_CONFLICT = "ATTEMPT_CONFLICT"
    TURN_NOT_RETRYABLE = "TURN_NOT_RETRYABLE"
    TURN_NOT_ABANDONABLE = "TURN_NOT_ABANDONABLE"
    RETRY_LIMIT_REACHED = "RETRY_LIMIT_REACHED"
    CONVERSATION_LIMIT_REACHED = "CONVERSATION_LIMIT_REACHED"
    TURN_LIMIT_REACHED = "TURN_LIMIT_REACHED"
    REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
    INVALID_REQUEST = "INVALID_REQUEST"
    RATE_LIMITED = "RATE_LIMITED"
    GENERATION_BUSY = "GENERATION_BUSY"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    PROVIDER_CONFIGURATION_INVALID = "PROVIDER_CONFIGURATION_INVALID"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    WORK_DEADLINE_EXCEEDED = "WORK_DEADLINE_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


HTTP_ERROR_STATUS = {
    code: (
        401 if code == HttpErrorCode.AUTHENTICATION_REQUIRED else
        403 if code in {HttpErrorCode.ORIGIN_REJECTED, HttpErrorCode.CSRF_FAILED} else
        404 if code in {HttpErrorCode.CONVERSATION_NOT_FOUND, HttpErrorCode.TURN_NOT_FOUND, HttpErrorCode.ASSISTANT_ROUTE_NOT_FOUND} else
        405 if code == HttpErrorCode.METHOD_NOT_ALLOWED else
        413 if code == HttpErrorCode.REQUEST_TOO_LARGE else
        422 if code == HttpErrorCode.INVALID_REQUEST else
        429 if code in {HttpErrorCode.RATE_LIMITED, HttpErrorCode.GENERATION_BUSY} else
        503 if code in {
            HttpErrorCode.PROVIDER_DISABLED, HttpErrorCode.PROVIDER_CONFIGURATION_INVALID,
            HttpErrorCode.DATABASE_UNAVAILABLE, HttpErrorCode.WORK_DEADLINE_EXCEEDED,
        } else 500 if code == HttpErrorCode.INTERNAL_ERROR else 409
    ) for code in HttpErrorCode
}

# Backend-authored catalogs only. Never interpolate inputs or upstream errors.
MAX_SAFE_ERROR_MESSAGE = 160
TURN_ERROR_MESSAGES = MappingProxyType({
    TurnResponseErrorCode.PROVIDER_TIMEOUT: "The assistant provider timed out. You can retry.",
    TurnResponseErrorCode.PROVIDER_UNAVAILABLE: "The assistant provider is unavailable. You can retry.",
    TurnResponseErrorCode.PROVIDER_RATE_LIMITED: "The assistant provider is busy. Try again later.",
    TurnResponseErrorCode.INVALID_PROVIDER_RESPONSE: "The assistant provider returned an invalid response. You can retry.",
    TurnResponseErrorCode.CONTEXT_UNAVAILABLE: "Financial context could not be loaded. You can retry.",
    TurnResponseErrorCode.SESSION_INVALIDATED: "Your session is no longer valid. Sign in before retrying.",
    TurnResponseErrorCode.INTERNAL_FAILURE: "The assistant could not finish this attempt. You can retry.",
    TurnResponseErrorCode.CONTEXT_LIMIT: "The required financial context exceeds the assistant's limits.",
    TurnResponseErrorCode.FINANCIAL_INVARIANT: "The financial context could not be verified.",
    TurnResponseErrorCode.OUTPUT_REJECTED: "The assistant response could not be verified.",
    TurnResponseErrorCode.GENERATION_INTERRUPTED: "Generation was interrupted. Retry if available, or abandon this turn.",
})
HTTP_ERROR_MESSAGES = MappingProxyType({
    HttpErrorCode.AUTHENTICATION_REQUIRED: "Authentication required",
    HttpErrorCode.ORIGIN_REJECTED: "Request origin is not allowed",
    HttpErrorCode.CSRF_FAILED: "CSRF validation failed",
    HttpErrorCode.CONVERSATION_NOT_FOUND: "Conversation not found.",
    HttpErrorCode.TURN_NOT_FOUND: "Turn not found.",
    HttpErrorCode.ASSISTANT_ROUTE_NOT_FOUND: "Assistant route not found.",
    HttpErrorCode.METHOD_NOT_ALLOWED: "Method not allowed.",
    HttpErrorCode.CONVERSATION_CREATE_CONFLICT: "Conversation creation attributes conflict with the existing conversation.",
    HttpErrorCode.IDEMPOTENCY_CONFLICT: "The operation key was already used for a different request.",
    HttpErrorCode.UNRESOLVED_TURN: "Resolve the existing pending or failed turn before submitting another message.",
    HttpErrorCode.ATTEMPT_CONFLICT: "The turn attempt has changed. Retrieve its current state.",
    HttpErrorCode.TURN_NOT_RETRYABLE: "This turn cannot be retried.",
    HttpErrorCode.TURN_NOT_ABANDONABLE: "This turn cannot be abandoned.",
    HttpErrorCode.RETRY_LIMIT_REACHED: "The retry limit has been reached.",
    HttpErrorCode.CONVERSATION_LIMIT_REACHED: "The conversation limit has been reached.",
    HttpErrorCode.TURN_LIMIT_REACHED: "The conversation's turn limit has been reached.",
    HttpErrorCode.REQUEST_TOO_LARGE: "The request body exceeds the size limit.",
    HttpErrorCode.INVALID_REQUEST: "Invalid request",
    HttpErrorCode.RATE_LIMITED: "Too many assistant requests. Try again later.",
    HttpErrorCode.GENERATION_BUSY: "Assistant generation capacity is busy. Try again later.",
    HttpErrorCode.PROVIDER_DISABLED: "The assistant provider is disabled.",
    HttpErrorCode.PROVIDER_CONFIGURATION_INVALID: "The assistant provider configuration is invalid.",
    HttpErrorCode.DATABASE_UNAVAILABLE: "Assistant storage is unavailable. Resolve any pending operation before resubmitting.",
    HttpErrorCode.WORK_DEADLINE_EXCEEDED: "Assistant work exceeded its deadline. Resolve any pending operation before resubmitting.",
    HttpErrorCode.INTERNAL_ERROR: "The assistant request could not be completed. Resolve any pending operation before resubmitting.",
})


class Topic(StrEnum):
    SUMMARY = "summary"
    ACCOUNTS = "accounts"
    CASH_FLOW = "cash_flow"
    SPENDING = "spending"
    BUDGETS = "budgets"
    GOALS = "goals"
    CATEGORY_COMPARISON = "category_comparison"
    RECENT_TRANSACTIONS = "recent_transactions"
    AFFORDABILITY_CONTEXT = "affordability_context"
    UNSUPPORTED = "unsupported"


class ProviderKind(StrEnum):
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    HOSTED = "hosted"
    FAKE = "fake"  # Identity only: never a production selection mode.


class ProviderFailureKind(StrEnum):
    TIMEOUT = "Timeout"
    UNAVAILABLE = "Unavailable"
    RATE_LIMITED = "RateLimited"
    INVALID_RESPONSE = "InvalidResponse"
    CONFIGURATION_ERROR = "ConfigurationError"


def scalar_text(value: object) -> str:
    if not isinstance(value, str) or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("Expected Unicode scalar text")
    if "\x00" in value:
        raise ValueError("NUL is not allowed")
    return value


def normalize_content(value: object) -> str:
    text = scalar_text(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 1 <= len(text) <= MAX_CONTENT_SCALARS:
        raise ValueError("Content must contain 1–4000 normalized scalar values")
    return text


def normalize_title(value: object) -> str | None:
    if value is None:
        return None
    text = scalar_text(value).strip()
    if not 1 <= len(text) <= 160:
        raise ValueError("Title must contain 1–160 trimmed scalar values")
    return text


def canonical_uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise ValueError("Expected a canonical UUID")
    parsed = UUID(value)
    if str(parsed) != value:
        raise ValueError("Expected a lowercase canonical UUID")
    return parsed


def canonical_uuid4(value: object) -> UUID:
    parsed = canonical_uuid(value)
    if parsed.version != 4:
        raise ValueError("Expected UUIDv4")
    return parsed


def utc_timestamp(value: object) -> datetime:
    if isinstance(value, str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value):
            raise ValueError("Expected UTC RFC3339 timestamp")
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("Expected UTC timestamp")
    return value


def iso_date(value: object) -> date:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    if type(value) is date:
        return value
    raise ValueError("Expected ISO date-only value")


def enum_input(enum_type):
    def validate(value):
        if not isinstance(value, (str, enum_type)):
            raise ValueError("Expected enum string")
        return enum_type(value)
    return BeforeValidator(validate)


CanonicalUUID = Annotated[UUID, BeforeValidator(canonical_uuid)]
UUIDv4 = Annotated[UUID, BeforeValidator(canonical_uuid4)]
Timestamp = Annotated[datetime, BeforeValidator(utc_timestamp)]
FinancialDate = Annotated[date, BeforeValidator(iso_date)]
Text = Annotated[str, BeforeValidator(scalar_text)]
Content = Annotated[str, BeforeValidator(normalize_content)]
Attempt = Annotated[int, Field(strict=True, ge=1, le=MAX_ATTEMPTS)]
Sequence = Annotated[int, Field(strict=True, ge=1, le=2**31 - 1)]
Status = Annotated[TurnStatus, enum_input(TurnStatus)]
Failure = Annotated[PersistedFailureCode, enum_input(PersistedFailureCode)]
ResponseCode = Annotated[TurnResponseErrorCode, enum_input(TurnResponseErrorCode)]
HttpCode = Annotated[HttpErrorCode, enum_input(HttpErrorCode)]
TopicValue = Annotated[Topic, enum_input(Topic)]
Kind = Annotated[ProviderKind, enum_input(ProviderKind)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ConversationCreateRequest(ContractModel):
    id: UUIDv4
    title: Annotated[str | None, BeforeValidator(normalize_title)] = None


class MessageSubmitRequest(ContractModel):
    content: Content


class AttemptRequest(ContractModel):
    expected_attempt_no: Attempt


class PaginationRequest(ContractModel):
    offset: Annotated[int, Field(strict=True, ge=0)] = 0
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 50


class MessageTurnMetadata(ContractModel):
    id: CanonicalUUID
    status: Status
    attempt_no: Attempt


class MessageDto(ContractModel):
    id: CanonicalUUID
    conversation_id: CanonicalUUID
    sequence_no: Sequence
    role: Literal["user", "assistant"]
    content: Annotated[Text, Field(min_length=1)]
    created_at: Timestamp
    turn: MessageTurnMetadata | None

    @model_validator(mode="after")
    def nonblank(self):
        if not self.content.strip():
            raise ValueError("Message cannot be blank")
        return self


class TurnError(ContractModel):
    code: ResponseCode
    message: Annotated[Text, Field(min_length=1, max_length=MAX_SAFE_ERROR_MESSAGE)]

    @model_validator(mode="after")
    def safe_message(self):
        if self.message != TURN_ERROR_MESSAGES[self.code]:
            raise ValueError("Turn error message must match the backend catalog")
        return self


class LifecycleProjection(ContractModel):
    lease_expired: bool
    can_retry: bool
    can_abandon: bool
    error_code: ResponseCode | None


class TurnDto(ContractModel):
    id: CanonicalUUID
    conversation_id: CanonicalUUID
    idempotency_key: UUIDv4
    status: Status
    attempt_no: Attempt
    user_message: MessageDto
    assistant_message: MessageDto | None
    created_at: Timestamp
    attempt_started_at: Timestamp
    attempt_finished_at: Timestamp | None
    lease_expires_at: Timestamp | None
    context_as_of: Timestamp | None
    financial_date: FinancialDate | None
    lease_expired: bool
    can_retry: bool
    can_abandon: bool
    error: TurnError | None

    @model_validator(mode="after")
    def coherent_turn(self):
        if self.created_at > self.attempt_started_at:
            raise ValueError("Attempt precedes creation")
        for instant in (self.attempt_finished_at, self.context_as_of):
            if instant is not None and instant < self.attempt_started_at:
                raise ValueError("Attempt metadata precedes attempt")
        if (self.context_as_of is None) != (self.financial_date is None):
            raise ValueError("Context observation and financial date must be paired")
        if self.context_as_of is not None:
            if self.context_as_of.astimezone(ZoneInfo("Asia/Kolkata")).date() != self.financial_date:
                raise ValueError("Financial date must use Asia/Kolkata observation date")
        user = self.user_message
        if user.role != "user" or user.sequence_no >= 2**31 - 1:
            raise ValueError("Invalid user message role/sequence")
        if normalize_content(user.content) != user.content:
            raise ValueError("Turn user content must already be normalized")
        for message in (user, self.assistant_message):
            if message is None:
                continue
            if message.conversation_id != self.conversation_id:
                raise ValueError("Message belongs to another conversation")
            if message.turn is None or (
                message.turn.id, message.turn.status, message.turn.attempt_no
            ) != (self.id, self.status, self.attempt_no):
                raise ValueError("Turn message metadata does not match")
        pending = self.status == TurnStatus.PENDING
        completed = self.status == TurnStatus.COMPLETED
        if pending:
            if self.lease_expires_at is None or self.lease_expires_at <= self.attempt_started_at:
                raise ValueError("Pending requires a lease after attempt start")
            if self.attempt_finished_at is not None or self.assistant_message is not None:
                raise ValueError("Pending cannot contain a result")
            code = TurnResponseErrorCode.GENERATION_INTERRUPTED if self.lease_expired else None
            retry, abandon = self.lease_expired and self.attempt_no < MAX_ATTEMPTS, self.lease_expired
        else:
            if self.lease_expires_at is not None or self.attempt_finished_at is None or self.lease_expired:
                raise ValueError("Resolved state requires finish and no lease")
            if completed != (self.assistant_message is not None):
                raise ValueError("Only completed turns have an assistant reply")
            if self.status == TurnStatus.FAILED:
                if self.error is None:
                    raise ValueError("Failed requires a persisted failure")
                failure = PersistedFailureCode(self.error.code.value)
                code = self.error.code
                retry, abandon = failure in RETRYABLE_FAILURES and self.attempt_no < MAX_ATTEMPTS, True
            else:
                code, retry, abandon = None, False, False
        if (self.error.code if self.error else None) != code:
            raise ValueError("Error is inconsistent with lifecycle state")
        if (self.can_retry, self.can_abandon) != (retry, abandon):
            raise ValueError("Action flags are inconsistent with lifecycle state")
        if completed:
            reply = self.assistant_message
            if self.context_as_of is None or reply.role != "assistant" or reply.sequence_no != user.sequence_no + 1:
                raise ValueError("Completed requires context and the reserved assistant reply")
        return self


class ConversationDto(ContractModel):
    id: CanonicalUUID
    title: Annotated[str | None, BeforeValidator(normalize_title)]
    created_at: Timestamp
    updated_at: Timestamp
    last_sequence_no: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
    unresolved_turn: TurnDto | None

    @model_validator(mode="after")
    def coherent_conversation(self):
        if self.updated_at < self.created_at:
            raise ValueError("Update precedes creation")
        turn = self.unresolved_turn
        if turn is not None and (
            turn.conversation_id != self.id or turn.status not in {TurnStatus.PENDING, TurnStatus.FAILED}
            or turn.user_message.sequence_no > self.last_sequence_no
        ):
            raise ValueError("Invalid unresolved turn")
        return self


T = TypeVar("T")


class PageDto(ContractModel, Generic[T]):
    items: list[T]
    total: Annotated[int, Field(strict=True, ge=0)]
    offset: Annotated[int, Field(strict=True, ge=0)]
    limit: Annotated[int, Field(strict=True, ge=1, le=100)]

    @model_validator(mode="after")
    def coherent_page(self):
        if len(self.items) > self.limit or len(self.items) > max(0, self.total - self.offset):
            raise ValueError("Page items exceed pagination bounds")
        return self


ConversationPageDto = PageDto[ConversationDto]
MessagePageDto = PageDto[MessageDto]


class ErrorIssue(ContractModel):
    # Never echo unknown field names, rejected values or Pydantic error text.
    # Unrecognized/nested paths must be reported at the safe 'body' location.
    location: Literal[
        "body", "id", "title", "content", "conversation_id", "turn_id",
        "expected_attempt_no", "offset", "limit", "Idempotency-Key", "Content-Encoding",
    ]
    message: Literal["Invalid value", "Required field", "Unexpected field"]


class ErrorDto(ContractModel):
    detail: Annotated[Text, Field(min_length=1, max_length=MAX_SAFE_ERROR_MESSAGE)]
    code: HttpCode
    issues: list[ErrorIssue]
    current_turn: TurnDto | None

    @model_validator(mode="after")
    def restrict_current_turn(self):
        if self.issues and self.code != HttpErrorCode.INVALID_REQUEST:
            raise ValueError("Field issues belong only to request validation errors")
        if self.detail != HTTP_ERROR_MESSAGES[self.code]:
            raise ValueError("HTTP error detail must match the backend catalog")
        if self.current_turn is not None and self.code not in {
            HttpErrorCode.UNRESOLVED_TURN, HttpErrorCode.ATTEMPT_CONFLICT,
            HttpErrorCode.TURN_NOT_RETRYABLE, HttpErrorCode.TURN_NOT_ABANDONABLE,
            HttpErrorCode.RETRY_LIMIT_REACHED,
        }:
            raise ValueError("Current turn is forbidden for this error")
        return self


ClaimId = Annotated[str, Field(strict=True, min_length=1, max_length=80, pattern=r"^[\x00-\x7f]+$"), BeforeValidator(scalar_text)]


class ProviderOutput(ContractModel):
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    topic: TopicValue
    claim_ids: Annotated[list[ClaimId], Field(max_length=MAX_SELECTED_CLAIMS)]

    @model_validator(mode="after")
    def unique_supported_selection(self):
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("Duplicate claim IDs")
        if self.topic == Topic.UNSUPPORTED and self.claim_ids:
            raise ValueError("Unsupported topic must have no claims")
        return self


ModelName = Annotated[str, Field(min_length=1, max_length=160), BeforeValidator(normalize_title)]


class ProviderIdentity(ContractModel):
    """Internal identity may record fake; production selection cannot accept it."""

    kind: Kind
    model: ModelName


class ProductionProviderIdentity(ProviderIdentity):
    @model_validator(mode="after")
    def prohibit_fake(self):
        if self.kind == ProviderKind.FAKE:
            raise ValueError("fake is restricted to test composition")
        return self


class ProviderSelection(ContractModel):
    """Selection contract only, not wired into application/environment settings."""

    mode: Literal["disabled", "ollama", "llama_cpp", "hosted"] = "disabled"
    identity: ProductionProviderIdentity | None = None

    @model_validator(mode="after")
    def matching_identity(self):
        if self.mode == "disabled":
            if self.identity is not None:
                raise ValueError("Disabled selection has no executing identity")
        elif self.identity is None or self.identity.kind.value != self.mode:
            raise ValueError("Enabled selection requires a matching identity")
        return self
