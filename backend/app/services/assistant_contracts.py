"""Pure assistant contract helpers. No I/O, orchestration or lifecycle writes."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.schemas.assistant import (
    HTTP_ERROR_STATUS, MAX_ATTEMPTS, MAX_CLAIMS, MAX_PROVIDER_BYTES,
    MAX_REQUEST_BYTES, ContractModel, HttpErrorCode, LifecycleProjection,
    PersistedFailureCode, ProviderFailureKind, ProviderOutput, RETRYABLE_FAILURES,
    Topic, TurnDto, TurnResponseErrorCode, TurnStatus, canonical_uuid,
    canonical_uuid4, normalize_content, utc_timestamp,
)


class ContractViolation(ValueError):
    """Sanitized contract failure; never retain rejected input in its message."""

    def __init__(self, code: HttpErrorCode):
        self.code = code
        self.status_code = HTTP_ERROR_STATUS[code]
        super().__init__(code.value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Nonfinite JSON number")


def _decode_object(body: bytes):
    decoded = json.loads(
        body.decode("utf-8"), object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )
    if not isinstance(decoded, dict):
        raise ValueError("Expected JSON object")
    return decoded


def parse_request_body(
    chunks: Iterable[bytes], schema: type[ContractModel], *, content_encoding: str | None = None,
) -> ContractModel:
    """Bound raw chunks before JSON parsing, including unknown-length bodies.

    Future HTTP integration must also bound transport chunk reads; this helper
    cannot undo a caller's earlier allocation of an unbounded body.
    """
    if content_encoding is not None and content_encoding.lower() != "identity":
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
    body = bytearray()
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
        if len(body) + len(chunk) > MAX_REQUEST_BYTES:
            raise ContractViolation(HttpErrorCode.REQUEST_TOO_LARGE)
        body.extend(chunk)
    try:
        return schema.model_validate(_decode_object(bytes(body)))
    except (ValueError, RecursionError):
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST) from None


def parse_idempotency_header(raw_headers: Iterable[tuple[bytes, bytes]]) -> UUID:
    """Consume raw ASGI headers, preserving duplicate/case-varied occurrences."""
    values = [value for name, value in raw_headers if name.lower() == b"idempotency-key"]
    if len(values) != 1:
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST)
    try:
        return canonical_uuid4(values[0].decode("ascii"))
    except (ValueError, UnicodeError):
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST) from None


def canonical_submission_bytes(conversation_id: UUID | str, content: str) -> bytes:
    value = {
        "version": 1,
        "conversation_id": str(canonical_uuid(conversation_id)),
        "content": normalize_content(content),
    }
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def submission_fingerprint(conversation_id: UUID | str, content: str) -> bytes:
    return hashlib.sha256(canonical_submission_bytes(conversation_id, content)).digest()


class IdempotencyResult(StrEnum):
    REPLAY = "replay"
    CONFLICT = "conflict"


def compare_fingerprints(existing: bytes, requested: bytes) -> IdempotencyResult:
    """Caller must first resolve an owned user/key; this performs no lookup."""
    if any(type(value) is not bytes or len(value) != 32 for value in (existing, requested)):
        raise ValueError("Expected two SHA-256 digests")
    return IdempotencyResult.REPLAY if hmac.compare_digest(existing, requested) else IdempotencyResult.CONFLICT


def project_lifecycle(
    *, status: TurnStatus, attempt_no: int, lease_expires_at: datetime | None,
    error_code: PersistedFailureCode | None, observed_at: datetime,
) -> LifecycleProjection:
    """Project already-read state at caller-supplied DB time; never read a clock."""
    if not isinstance(status, TurnStatus) or type(attempt_no) is not int or not 1 <= attempt_no <= MAX_ATTEMPTS:
        raise ValueError("Invalid lifecycle status/attempt")
    now = utc_timestamp(observed_at)
    if error_code is not None and not isinstance(error_code, PersistedFailureCode):
        raise ValueError("Expected persisted failure code, never derived error")
    if status == TurnStatus.PENDING:
        if lease_expires_at is None or error_code is not None:
            raise ValueError("Pending requires lease and no persisted error")
        expired = now >= utc_timestamp(lease_expires_at)
        return LifecycleProjection(
            lease_expired=expired, can_retry=expired and attempt_no < MAX_ATTEMPTS,
            can_abandon=expired,
            error_code=TurnResponseErrorCode.GENERATION_INTERRUPTED if expired else None,
        )
    if lease_expires_at is not None or (status == TurnStatus.FAILED) != (error_code is not None):
        raise ValueError("Invalid resolved lease/failure state")
    return LifecycleProjection(
        lease_expired=False,
        can_retry=status == TurnStatus.FAILED and error_code in RETRYABLE_FAILURES and attempt_no < MAX_ATTEMPTS,
        can_abandon=status == TurnStatus.FAILED,
        error_code=TurnResponseErrorCode(error_code.value) if error_code is not None else None,
    )


def replay_http_status(turn: TurnDto) -> int:
    return 202 if turn.status == TurnStatus.PENDING and not turn.lease_expired else 200


class AttemptAction(StrEnum):
    REPLAY = "replay"
    CLAIM = "claim"  # A decision only; this helper never increments/writes.


def retry_contract(turn: TurnDto, expected_attempt_no: int) -> AttemptAction:
    _validate_expected(expected_attempt_no)
    if turn.attempt_no < expected_attempt_no:
        raise ContractViolation(HttpErrorCode.ATTEMPT_CONFLICT)
    if turn.attempt_no > expected_attempt_no or turn.status == TurnStatus.COMPLETED:
        return AttemptAction.REPLAY
    if turn.status == TurnStatus.ABANDONED:
        raise ContractViolation(HttpErrorCode.TURN_NOT_RETRYABLE)
    if turn.status == TurnStatus.PENDING and not turn.lease_expired:
        return AttemptAction.REPLAY
    if turn.attempt_no == MAX_ATTEMPTS:
        raise ContractViolation(HttpErrorCode.RETRY_LIMIT_REACHED)
    if not turn.can_retry:
        raise ContractViolation(HttpErrorCode.TURN_NOT_RETRYABLE)
    # SESSION_INVALIDATED eligibility does not authorize a request. The future
    # endpoint must reauthenticate before calling this pure contract helper.
    return AttemptAction.CLAIM


def abandon_contract(turn: TurnDto, expected_attempt_no: int) -> AttemptAction:
    _validate_expected(expected_attempt_no)
    if turn.attempt_no != expected_attempt_no:
        raise ContractViolation(HttpErrorCode.ATTEMPT_CONFLICT)
    if turn.status == TurnStatus.ABANDONED:
        return AttemptAction.REPLAY
    if not turn.can_abandon:
        raise ContractViolation(HttpErrorCode.TURN_NOT_ABANDONABLE)
    return AttemptAction.CLAIM


def _validate_expected(value):
    if type(value) is not int or not 1 <= value <= MAX_ATTEMPTS:
        raise ContractViolation(HttpErrorCode.INVALID_REQUEST)


@dataclass
class GroundingContractViolation(ValueError):
    code: PersistedFailureCode


def parse_provider_output(body: bytes) -> ProviderOutput:
    """Strict syntax only. Context-local claim authorization is a separate step."""
    if type(body) is not bytes or len(body) > MAX_PROVIDER_BYTES:
        raise GroundingContractViolation(PersistedFailureCode.INVALID_PROVIDER_RESPONSE)
    try:
        return ProviderOutput.model_validate(_decode_object(body))
    except (ValueError, RecursionError):
        raise GroundingContractViolation(PersistedFailureCode.INVALID_PROVIDER_RESPONSE) from None


def validate_claim_selection(
    output: ProviderOutput, *, allowed_topics: Mapping[str, frozenset[Topic]],
    required_ids: Mapping[Topic, frozenset[str]],
    exclusive_groups: tuple[frozenset[str], ...] = (),
) -> ProviderOutput:
    """Validate a supplied backend catalog policy, without creating/rendering claims.

    Catalog authoring, coverage evaluation, financial context and deterministic
    response rendering remain Phase 9D/9E responsibilities.
    """
    if len(allowed_topics) > MAX_CLAIMS:
        raise ValueError("Catalog exceeds contract bound")
    selected = frozenset(output.claim_ids)
    if output.topic == Topic.UNSUPPORTED:
        if selected:
            raise GroundingContractViolation(PersistedFailureCode.OUTPUT_REJECTED)
        return output
    if not selected <= allowed_topics.keys():
        raise GroundingContractViolation(PersistedFailureCode.INVALID_PROVIDER_RESPONSE)
    baseline = required_ids.get(output.topic)
    if not baseline:
        raise GroundingContractViolation(PersistedFailureCode.OUTPUT_REJECTED)
    if any(output.topic not in allowed_topics[key] for key in selected) or (
        not baseline <= selected
    ) or any(len(selected & group) > 1 for group in exclusive_groups):
        raise GroundingContractViolation(PersistedFailureCode.OUTPUT_REJECTED)
    return output


PROVIDER_FAILURE_CODES = {
    ProviderFailureKind.TIMEOUT: PersistedFailureCode.PROVIDER_TIMEOUT,
    ProviderFailureKind.UNAVAILABLE: PersistedFailureCode.PROVIDER_UNAVAILABLE,
    ProviderFailureKind.RATE_LIMITED: PersistedFailureCode.PROVIDER_RATE_LIMITED,
    ProviderFailureKind.INVALID_RESPONSE: PersistedFailureCode.INVALID_PROVIDER_RESPONSE,
}
# ConfigurationError is an HTTP 503 admission error, not a new persisted code.
