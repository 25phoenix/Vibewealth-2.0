"""Deterministic Phase 9C.1 contracts: no database, network or model required."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.assistant import (
    HTTP_ERROR_MESSAGES, HTTP_ERROR_STATUS, MAX_ATTEMPTS, MAX_PROVIDER_BYTES, MAX_REQUEST_BYTES,
    MAX_SAFE_ERROR_MESSAGE, TURN_ERROR_MESSAGES,
    AttemptRequest, ConversationCreateRequest, ConversationDto, ErrorDto, ErrorIssue,
    HttpErrorCode, MessageDto, MessageSubmitRequest, PageDto, PaginationRequest,
    PersistedFailureCode, ProductionProviderIdentity, ProviderIdentity,
    ProviderKind, ProviderOutput, ProviderSelection, RETRYABLE_FAILURES, Topic,
    TurnDto, TurnError, TurnResponseErrorCode, TurnStatus,
)
from app.services.assistant_contracts import (
    PROVIDER_FAILURE_CODES, AttemptAction, ContractViolation,
    GroundingContractViolation, IdempotencyResult, abandon_contract,
    canonical_submission_bytes, compare_fingerprints, parse_idempotency_header,
    parse_provider_output, parse_request_body, project_lifecycle,
    replay_http_status, retry_contract, submission_fingerprint,
    validate_claim_selection,
)

CID = "123e4567-e89b-42d3-a456-426614174000"
TID = "223e4567-e89b-42d3-a456-426614174000"
KEY = "323e4567-e89b-42d3-a456-426614174000"
NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Assistant contract attempted network access")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def turn_payload(status="pending", attempt=1, *, expired=False, failure="PROVIDER_TIMEOUT"):
    lease = NOW if expired else NOW + timedelta(seconds=90)
    projection = project_lifecycle(
        status=TurnStatus(status), attempt_no=attempt,
        lease_expires_at=lease if status == "pending" else None,
        error_code=PersistedFailureCode(failure) if status == "failed" else None,
        observed_at=NOW,
    )
    metadata = {"id": TID, "status": status, "attempt_no": attempt}
    user = {
        "id": KEY, "conversation_id": CID, "sequence_no": 1, "role": "user",
        "content": "Show my budgets", "created_at": NOW, "turn": metadata,
    }
    reply = {
        **user, "id": CID, "sequence_no": 2, "role": "assistant",
        "content": "Backend-rendered answer",
    } if status == "completed" else None
    return {
        "id": TID, "conversation_id": CID, "idempotency_key": KEY,
        "status": status, "attempt_no": attempt, "user_message": user,
        "assistant_message": reply, "created_at": NOW - timedelta(minutes=1),
        "attempt_started_at": NOW - timedelta(seconds=1),
        "attempt_finished_at": None if status == "pending" else NOW,
        "lease_expires_at": lease if status == "pending" else None,
        "context_as_of": NOW if status == "completed" else None,
        "financial_date": NOW.date() if status == "completed" else None,
        "lease_expired": projection.lease_expired,
        "can_retry": projection.can_retry, "can_abandon": projection.can_abandon,
        "error": {"code": projection.error_code.value, "message": TURN_ERROR_MESSAGES[projection.error_code]}
        if projection.error_code else None,
    }


def make_turn(*args, **kwargs):
    return TurnDto.model_validate(turn_payload(*args, **kwargs))


def assert_contract_error(code, fn, *args, **kwargs):
    with pytest.raises(ContractViolation) as caught:
        fn(*args, **kwargs)
    assert caught.value.code == code
    assert caught.value.status_code == HTTP_ERROR_STATUS[code]
    assert str(caught.value) == code.value


def test_golden_fingerprint_exact_bytes_and_digest():
    expected = (
        '{"content":"Show ₹100 \\"budget\\".",'
        '"conversation_id":"123e4567-e89b-42d3-a456-426614174000","version":1}'
    ).encode("utf-8")
    actual = canonical_submission_bytes(CID, ' \r\nShow ₹100 "budget".\r\n ')
    assert actual == expected
    assert len(actual) == 106
    assert submission_fingerprint(CID, 'Show ₹100 "budget".').hex() == (
        "2570b775ad4bf225cf7c39bfa536ceb5d0f181bd8143f3982eaecfe2e26d1f99"
    )


def test_fingerprint_ignores_insertion_order_and_wire_escaping():
    first = parse_request_body([b'{"content":"Show \\u20b9100 \\"budget\\"."}'], MessageSubmitRequest)
    second = parse_request_body(['{ "content" : "Show ₹100 \\"budget\\"." }'.encode()], MessageSubmitRequest)
    assert first.content == second.content == 'Show \u20b9100 "budget".'
    assert submission_fingerprint(UUID(CID), first.content) == submission_fingerprint(CID, second.content)
    decoded = json.loads(canonical_submission_bytes(CID, first.content))
    assert list(decoded) == ["content", "conversation_id", "version"]


def test_canonical_controls_and_unicode_are_not_normalized():
    encoded = canonical_submission_bytes(CID, 'x\b\f\n\r\t\x01/\u2028\u2029😀"\\y')
    assert b'x\\b\\f\\n\\n\\t\\u0001/' in encoded
    assert '\u2028\u2029😀'.encode() in encoded
    assert b'\\"\\\\y' in encoded
    assert submission_fingerprint(CID, "é") != submission_fingerprint(CID, "e\u0301")
    assert submission_fingerprint(CID, "a b") != submission_fingerprint(CID, "a  b")
    assert submission_fingerprint(CID, "x") != submission_fingerprint(TID, "x")


@pytest.mark.parametrize("payload", [
    {}, {"content": ""}, {"content": " \r\n "}, {"content": 1},
    {"content": True}, {"content": None}, {"content": "x", "user_id": CID},
    {"content": "x\x00"}, {"content": "\ud800"}, {"content": "x" * 4001},
])
def test_reject_invalid_message_payloads(payload):
    with pytest.raises(ValidationError):
        MessageSubmitRequest.model_validate(payload)


@pytest.mark.parametrize("scalar", ["x", "\u20b9", "\U0001f600", '"', "\\", "\x01"])
@pytest.mark.parametrize("escaped", [False, True])
def test_content_wire_boundaries(scalar, escaped):
    text = scalar * 4000
    body = json.dumps({"content": text}, ensure_ascii=escaped, separators=(",", ":")).encode()
    if scalar == "\U0001f600":
        assert len(text) == 4000 and len(text.encode("utf-8")) == 16000
        assert len(body) == (48014 if escaped else 16014)
    assert len(body) <= MAX_REQUEST_BYTES
    assert parse_request_body([body[:3], body[3:]], MessageSubmitRequest).content == text


def test_bounded_parser_accepts_exact_limit_and_stops_on_first_overflow():
    body = b'{"content":"x"}'
    assert parse_request_body([body, b" " * (MAX_REQUEST_BYTES - len(body))], MessageSubmitRequest).content == "x"

    def overflow():
        yield body
        yield b" " * MAX_REQUEST_BYTES
        pytest.fail("Parser consumed beyond overflow")

    assert_contract_error(HttpErrorCode.REQUEST_TOO_LARGE, parse_request_body, overflow(), MessageSubmitRequest)


@pytest.mark.parametrize("streamed", [False, True])
def test_request_body_rejects_exactly_65537_bytes(streamed):
    body = b'{"content":"x"}'
    oversized = body + b" " * (65537 - len(body))
    assert len(oversized) == MAX_REQUEST_BYTES + 1 == 65537
    chunks = [oversized[:65536], oversized[65536:]] if streamed else [oversized]
    assert_contract_error(HttpErrorCode.REQUEST_TOO_LARGE, parse_request_body, chunks, MessageSubmitRequest)


@pytest.mark.parametrize("body", [
    b'{"content":"x","content":"y"}', b'{"content":"\\ud800"}',
    b'{"content":"\xff"}', b'\xef\xbb\xbf{"content":"x"}', b'[]',
    b'{"content":NaN}', b'{"content":"x"} trailing', b'{"content":"x"',
    b'{"content": {"x":1,"x":2}}',
])
def test_invalid_json_is_sanitized(body):
    assert_contract_error(HttpErrorCode.INVALID_REQUEST, parse_request_body, [body], MessageSubmitRequest)


def test_encoding_restrictions():
    assert parse_request_body([b'{"content":"x"}'], MessageSubmitRequest, content_encoding="identity").content == "x"
    assert_contract_error(HttpErrorCode.INVALID_REQUEST, parse_request_body, [], MessageSubmitRequest, content_encoding="gzip")


def test_maximum_scalar_count_is_independent_of_utf8_bytes():
    assert len(MessageSubmitRequest(content="😀" * 4000).content) == 4000
    with pytest.raises(ValidationError):
        MessageSubmitRequest(content="😀" * 4001)


def test_fingerprint_rejects_invalid_inputs_instead_of_coercing():
    for value in (CID.upper(), CID.replace("-", ""), 1, True):
        with pytest.raises(ValueError):
            canonical_submission_bytes(value, "x")
    for content in (None, 1, "\ud800", "x\x00", " "):
        with pytest.raises(ValueError):
            canonical_submission_bytes(CID, content)


@pytest.mark.parametrize("value", [CID.upper(), CID.replace("-", ""), " " + CID, "not-uuid", 1, True,
                                    "123e4567-e89b-12d3-a456-426614174000"])
def test_create_uuid_is_canonical_v4(value):
    with pytest.raises(ValidationError):
        ConversationCreateRequest(id=value)


def test_conversation_create_title_and_defaults():
    assert ConversationCreateRequest(id=CID).title is None
    assert ConversationCreateRequest(id=CID, title=" \u2003Budget\r\n ").title == "Budget"
    assert len(ConversationCreateRequest(id=CID, title="😀" * 160).title) == 160
    for title in (" ", "x" * 161, 1, "\udfff", "\x00"):
        with pytest.raises(ValidationError):
            ConversationCreateRequest(id=CID, title=title)
    with pytest.raises(ValidationError):
        ConversationCreateRequest(id=CID, owner_id=KEY)


def test_header_validation_preserves_duplicate_occurrences():
    assert parse_idempotency_header([(b"IDEMPOTENCY-KEY", KEY.encode())]) == UUID(KEY)
    invalid = [[], [(b"Idempotency-Key", b"bad")],
               [(b"idempotency-key", KEY.encode()), (b"Idempotency-Key", KEY.encode())],
               [(b"idempotency-key", (KEY + "," + KEY).encode())],
               [(b"idempotency-key", KEY.upper().encode())],
               [(b"idempotency-key", b"\xff")],
               [(b"idempotency-key", b"123e4567-e89b-12d3-a456-426614174000")]]
    for headers in invalid:
        assert_contract_error(HttpErrorCode.INVALID_REQUEST, parse_idempotency_header, headers)


@pytest.mark.parametrize("value", [True, 1.0, "1", 0, 4, None])
def test_strict_attempt(value):
    with pytest.raises(ValidationError):
        AttemptRequest(expected_attempt_no=value)


def test_strict_pagination():
    assert PaginationRequest().model_dump() == {"offset": 0, "limit": 50}
    for payload in ({"offset": -1}, {"limit": 101}, {"limit": 0}, {"offset": "0"}, {"limit": True}, {"extra": 1}):
        with pytest.raises(ValidationError):
            PaginationRequest.model_validate(payload)
    assert PageDto[MessageDto](items=[], total=1, offset=100, limit=50).items == []
    with pytest.raises(ValidationError):
        PageDto[MessageDto](items=[make_turn().user_message], total=0, offset=0, limit=50)


@pytest.mark.parametrize("status", list(TurnStatus))
def test_all_lifecycle_dtos_round_trip(status):
    turn = make_turn(status.value)
    assert TurnDto.model_validate_json(turn.model_dump_json()) == turn
    assert turn.status == status
    assert turn.can_abandon == (status == TurnStatus.FAILED)


def test_interruption_is_derived_at_exact_expiry_and_not_a_persisted_state():
    assert "GENERATION_INTERRUPTED" not in {value.value for value in PersistedFailureCode}
    assert "GENERATION_INTERRUPTED" not in {value.value for value in TurnStatus}
    before = project_lifecycle(status=TurnStatus.PENDING, attempt_no=1, lease_expires_at=NOW,
                               error_code=None, observed_at=NOW - timedelta(microseconds=1))
    assert not before.lease_expired and not before.can_retry
    expired = make_turn(expired=True)
    assert expired.status == TurnStatus.PENDING
    assert expired.error.code == TurnResponseErrorCode.GENERATION_INTERRUPTED
    assert expired.can_retry and expired.can_abandon
    assert replay_http_status(expired) == 200
    assert replay_http_status(make_turn()) == 202
    assert not make_turn(attempt=3, expired=True).can_retry


@pytest.mark.parametrize("failure", list(PersistedFailureCode))
@pytest.mark.parametrize("attempt", [1, 3])
def test_failure_retry_policy(failure, attempt):
    turn = make_turn("failed", attempt, failure=failure.value)
    assert turn.can_retry == (failure in RETRYABLE_FAILURES and attempt < MAX_ATTEMPTS)
    assert turn.can_abandon
    assert turn.error.code.value == failure.value


def test_session_invalidated_is_not_provider_failure_or_permission_to_write():
    assert PersistedFailureCode.SESSION_INVALIDATED not in PROVIDER_FAILURE_CODES.values()
    turn = make_turn("failed", failure="SESSION_INVALIDATED")
    assert turn.can_retry  # Only eligibility; endpoint authentication is deferred.
    assert retry_contract(turn, 1) == AttemptAction.CLAIM
    assert HTTP_ERROR_STATUS[HttpErrorCode.AUTHENTICATION_REQUIRED] == 401


@pytest.mark.parametrize("updates", [
    {"status": "interrupted"}, {"attempt_no": True}, {"attempt_no": 4},
    {"can_retry": True}, {"can_abandon": True}, {"lease_expires_at": None},
    {"lease_expired": True}, {"context_as_of": NOW}, {"extra": 1},
    {"attempt_started_at": NOW - timedelta(days=1)},
    {"error": {"code": "PROVIDER_TIMEOUT", "message": TURN_ERROR_MESSAGES[TurnResponseErrorCode.PROVIDER_TIMEOUT]}},
])
def test_reject_incoherent_pending_response(updates):
    with pytest.raises(ValidationError):
        TurnDto.model_validate({**turn_payload(), **updates})


def test_response_message_links_dates_and_abandonment_are_strict():
    for status in ("completed", "failed", "abandoned"):
        payload = turn_payload(status)
        payload["lease_expires_at"] = NOW
        with pytest.raises(ValidationError):
            TurnDto.model_validate(payload)
    payload = turn_payload("abandoned")
    payload["error"] = {"code": "PROVIDER_TIMEOUT", "message": TURN_ERROR_MESSAGES[TurnResponseErrorCode.PROVIDER_TIMEOUT]}
    with pytest.raises(ValidationError):
        TurnDto.model_validate(payload)


@pytest.mark.parametrize("field", list(turn_payload().keys()))
def test_turn_response_requires_every_field_even_nullable(field):
    payload = turn_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        TurnDto.model_validate(payload)


@pytest.mark.parametrize("status,error,lease,attempt", [
    (TurnStatus.ABANDONED, PersistedFailureCode.PROVIDER_TIMEOUT, None, 1),
    (TurnStatus.COMPLETED, None, NOW, 1),
    (TurnStatus.FAILED, None, None, 1),
    (TurnStatus.PENDING, PersistedFailureCode.PROVIDER_TIMEOUT, NOW, 1),
    (TurnStatus.PENDING, None, None, 1),
    (TurnStatus.PENDING, None, NOW, True),
    (TurnStatus.PENDING, TurnResponseErrorCode.GENERATION_INTERRUPTED, NOW, 1),
])
def test_projection_rejects_invalid_persisted_state(status, error, lease, attempt):
    with pytest.raises(ValueError):
        project_lifecycle(status=status, attempt_no=attempt, error_code=error,
                          lease_expires_at=lease, observed_at=NOW)


def test_completed_message_links_and_failed_derived_error():
    for field, bad in (("conversation_id", TID), ("role", "user"), ("sequence_no", 3), ("turn", None)):
        payload = turn_payload("completed")
        payload["assistant_message"][field] = bad
        with pytest.raises(ValidationError):
            TurnDto.model_validate(payload)
    payload = turn_payload("completed")
    payload["financial_date"] = "2026-11-14"
    with pytest.raises(ValidationError):
        TurnDto.model_validate(payload)
    payload = turn_payload("failed")
    payload["error"]["code"] = "GENERATION_INTERRUPTED"
    payload["error"]["message"] = TURN_ERROR_MESSAGES[TurnResponseErrorCode.GENERATION_INTERRUPTED]
    with pytest.raises(ValidationError):
        TurnDto.model_validate(payload)


def test_legacy_message_and_conversation_contracts():
    legacy = {**turn_payload()["user_message"], "turn": None}
    assert MessageDto.model_validate(legacy).turn is None
    payload = {"id": CID, "title": None, "created_at": NOW, "updated_at": NOW,
               "last_sequence_no": 1, "unresolved_turn": make_turn()}
    assert ConversationDto.model_validate(payload).unresolved_turn.status == TurnStatus.PENDING
    for turn in (make_turn("completed"), make_turn("abandoned")):
        with pytest.raises(ValidationError):
            ConversationDto.model_validate({**payload, "unresolved_turn": turn})


@pytest.mark.parametrize("field,value", [("sequence_no", True), ("sequence_no", "1"),
                                         ("created_at", "2026-11-15"),
                                         ("created_at", "2026-11-15T12:00:00+05:30"),
                                         ("content", " "), ("id", CID.upper())])
def test_message_response_strict_types(field, value):
    with pytest.raises(ValidationError):
        MessageDto.model_validate({**turn_payload()["user_message"], field: value})


def test_retry_and_abandon_contract_decisions_do_not_mutate_input():
    live = make_turn()
    original = live.model_dump_json()
    assert retry_contract(live, 1) == AttemptAction.REPLAY
    assert_contract_error(HttpErrorCode.TURN_NOT_ABANDONABLE, abandon_contract, live, 1)
    assert_contract_error(HttpErrorCode.ATTEMPT_CONFLICT, retry_contract, live, 2)
    assert retry_contract(make_turn(attempt=2), 1) == AttemptAction.REPLAY
    assert_contract_error(HttpErrorCode.ATTEMPT_CONFLICT, abandon_contract, make_turn(attempt=2), 1)
    assert retry_contract(make_turn(expired=True), 1) == AttemptAction.CLAIM
    assert abandon_contract(make_turn(expired=True), 1) == AttemptAction.CLAIM
    assert retry_contract(make_turn("completed"), 1) == AttemptAction.REPLAY
    assert abandon_contract(make_turn("abandoned"), 1) == AttemptAction.REPLAY
    assert_contract_error(HttpErrorCode.TURN_NOT_RETRYABLE, retry_contract, make_turn("abandoned"), 1)
    assert_contract_error(HttpErrorCode.RETRY_LIMIT_REACHED, retry_contract, make_turn(attempt=3, expired=True), 3)
    assert_contract_error(HttpErrorCode.TURN_NOT_RETRYABLE, retry_contract, make_turn("failed", failure="CONTEXT_LIMIT"), 1)
    assert live.model_dump_json() == original


def test_idempotency_replay_and_conflict():
    digest = submission_fingerprint(CID, "x")
    assert compare_fingerprints(digest, submission_fingerprint(CID, " x ")) == IdempotencyResult.REPLAY
    for other in (submission_fingerprint(TID, "x"), submission_fingerprint(CID, "y")):
        assert compare_fingerprints(digest, other) == IdempotencyResult.CONFLICT
    with pytest.raises(ValueError):
        compare_fingerprints(b"wrong-length", digest)


@pytest.mark.parametrize("code", list(HttpErrorCode))
def test_http_error_contract(code):
    dto = ErrorDto(detail=HTTP_ERROR_MESSAGES[code], code=code.value, issues=[], current_turn=None)
    assert ErrorDto.model_validate_json(dto.model_dump_json()) == dto
    assert 400 <= HTTP_ERROR_STATUS[code] <= 599


def test_error_details_and_field_issues_preserve_client_contract():
    for code in ("AUTHENTICATION_REQUIRED", "CSRF_FAILED", "ORIGIN_REJECTED"):
        with pytest.raises(ValidationError):
            ErrorDto(detail="Different detail", code=code, issues=[], current_turn=None)
    with pytest.raises(ValidationError):
        ErrorDto(detail=HTTP_ERROR_MESSAGES[HttpErrorCode.GENERATION_BUSY], code="GENERATION_BUSY", current_turn=None,
                 issues=[{"location": "content", "message": "Invalid value"}])
    assert ErrorDto(detail="Invalid request", code="INVALID_REQUEST", current_turn=None,
                    issues=[{"location": "content", "message": "Invalid value"}]).issues


@pytest.mark.parametrize("content", [" untrimmed ", "x\r\ny", "x" * 4001])
def test_turn_response_cannot_reintroduce_noncanonical_user_content(content):
    payload = turn_payload()
    payload["user_message"]["content"] = content
    with pytest.raises(ValidationError):
        TurnDto.model_validate(payload)


def test_unresolved_and_capacity_errors_remain_distinct():
    turn = make_turn()
    unresolved = ErrorDto(detail=HTTP_ERROR_MESSAGES[HttpErrorCode.UNRESOLVED_TURN], code="UNRESOLVED_TURN", issues=[], current_turn=turn)
    assert unresolved.current_turn == turn
    assert HTTP_ERROR_STATUS[unresolved.code] == 409
    assert HTTP_ERROR_STATUS[HttpErrorCode.GENERATION_BUSY] == 429
    with pytest.raises(ValidationError):
        ErrorDto(detail=HTTP_ERROR_MESSAGES[HttpErrorCode.GENERATION_BUSY], code="GENERATION_BUSY", issues=[], current_turn=turn)


@pytest.mark.parametrize("payload", [
    {"version": True, "topic": "summary", "claim_ids": []},
    {"version": "1", "topic": "summary", "claim_ids": []},
    {"version": 2, "topic": "summary", "claim_ids": []},
    {"version": 1, "topic": "unknown", "claim_ids": []},
    {"version": 1, "topic": "summary", "claim_ids": ["x", "x"]},
    {"version": 1, "topic": "summary", "claim_ids": ["₹"]},
    {"version": 1, "topic": "summary", "claim_ids": [""]},
    {"version": 1, "topic": "summary", "claim_ids": ["x" * 81]},
    {"version": 1, "topic": "summary", "claim_ids": [str(i) for i in range(13)]},
    {"version": 1, "topic": "summary", "claim_ids": [], "amount_paise": 10},
    {"version": 1, "topic": "summary", "claim_ids": [], "prose": "Invented answer"},
    {"version": 1, "topic": "unsupported", "claim_ids": ["x"]},
    {"version": 1, "topic": "summary", "claim_ids": [{"amount": 1}]},
])
def test_grounding_schema_rejects_unrestricted_or_invalid_output(payload):
    with pytest.raises(ValidationError):
        ProviderOutput.model_validate(payload)


def test_question_mark_is_a_valid_ascii_claim_id_but_still_requires_catalog_membership():
    output = ProviderOutput(version=1, topic="summary", claim_ids=["?"])
    assert output.claim_ids == ["?"]
    assert validate_claim_selection(
        output, allowed_topics={"?": frozenset({Topic.SUMMARY})},
        required_ids={Topic.SUMMARY: frozenset({"?"})},
    ) == output
    with pytest.raises(GroundingContractViolation) as caught:
        validate_claim_selection(output, allowed_topics={}, required_ids={Topic.SUMMARY: frozenset({"?"})})
    assert caught.value.code == PersistedFailureCode.INVALID_PROVIDER_RESPONSE


@pytest.mark.parametrize("topic", [topic for topic in Topic if topic != Topic.UNSUPPORTED])
@pytest.mark.parametrize("baseline", [None, frozenset(), frozenset({"baseline"})])
def test_supported_topics_fail_closed_on_absent_empty_or_unselected_baseline(topic, baseline):
    output = ProviderOutput(version=1, topic=topic, claim_ids=["detail"])
    with pytest.raises(GroundingContractViolation) as caught:
        validate_claim_selection(
            output,
            allowed_topics={key: frozenset({topic}) for key in ("baseline", "detail")},
            required_ids={} if baseline is None else {topic: baseline},
        )
    assert caught.value.code == PersistedFailureCode.OUTPUT_REJECTED


@pytest.mark.parametrize("topic", [topic for topic in Topic if topic != Topic.UNSUPPORTED])
def test_supported_topic_requires_all_explicit_baseline_claims(topic):
    catalog = {key: frozenset({topic}) for key in ("baseline.a", "baseline.b", "detail")}
    required = {topic: frozenset({"baseline.a", "baseline.b"})}
    for ids in ([], ["baseline.a"], ["baseline.b", "detail"]):
        with pytest.raises(GroundingContractViolation) as caught:
            validate_claim_selection(ProviderOutput(version=1, topic=topic, claim_ids=ids),
                                     allowed_topics=catalog, required_ids=required)
        assert caught.value.code == PersistedFailureCode.OUTPUT_REJECTED
    complete = ProviderOutput(version=1, topic=topic, claim_ids=["baseline.a", "baseline.b"])
    assert validate_claim_selection(complete, allowed_topics=catalog, required_ids=required) == complete


def test_unsupported_needs_no_baseline_and_cannot_supply_claims():
    output = ProviderOutput(version=1, topic="unsupported", claim_ids=[])
    assert validate_claim_selection(output, allowed_topics={}, required_ids={}) == output
    with pytest.raises(ValidationError):
        ProviderOutput(version=1, topic="unsupported", claim_ids=["?"])


UNTRUSTED_ERROR_TEXT = [
    "upstream provider returned private model details",
    "Show my private account balances",
    "Authorization: Bearer synthetic-secret",
    "password=synthetic-password; cookie=synthetic-session",
    "x" * (MAX_SAFE_ERROR_MESSAGE + 1),
]


@pytest.mark.parametrize("code", list(TurnResponseErrorCode))
def test_turn_errors_accept_only_bounded_code_specific_backend_text(code):
    safe = TURN_ERROR_MESSAGES[code]
    assert 0 < len(safe) <= MAX_SAFE_ERROR_MESSAGE
    assert TurnError(code=code, message=safe).message == safe
    wrong_code = next(other for other in TurnResponseErrorCode if other != code)
    for unsafe in [*UNTRUSTED_ERROR_TEXT, TURN_ERROR_MESSAGES[wrong_code]]:
        with pytest.raises(ValidationError):
            TurnError(code=code, message=unsafe)
        with pytest.raises(ValidationError):
            TurnError.model_validate_json(json.dumps({"code": code.value, "message": unsafe}))


@pytest.mark.parametrize("code", list(HttpErrorCode))
def test_http_errors_reject_raw_or_other_code_text(code):
    safe = HTTP_ERROR_MESSAGES[code]
    assert 0 < len(safe) <= MAX_SAFE_ERROR_MESSAGE
    wrong_code = next(other for other in HttpErrorCode if other != code)
    for unsafe in [*UNTRUSTED_ERROR_TEXT, HTTP_ERROR_MESSAGES[wrong_code]]:
        payload = {"code": code.value, "detail": unsafe, "issues": [], "current_turn": None}
        with pytest.raises(ValidationError):
            ErrorDto.model_validate(payload)
        with pytest.raises(ValidationError):
            ErrorDto.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("unsafe", UNTRUSTED_ERROR_TEXT)
def test_validation_issues_reject_untrusted_messages_and_locations(unsafe):
    for issue in ({"location": "content", "message": unsafe},
                  {"location": unsafe, "message": "Invalid value"}):
        with pytest.raises(ValidationError):
            ErrorIssue.model_validate(issue)
        with pytest.raises(ValidationError):
            ErrorDto.model_validate({
                "code": "INVALID_REQUEST", "detail": HTTP_ERROR_MESSAGES[HttpErrorCode.INVALID_REQUEST],
                "issues": [issue], "current_turn": None,
            })
    assert ErrorIssue(location="body", message="Unexpected field").model_dump() == {
        "location": "body", "message": "Unexpected field",
    }


def test_error_catalogs_are_complete_and_authentication_details_are_unchanged():
    assert set(HTTP_ERROR_MESSAGES) == set(HttpErrorCode)
    assert set(TURN_ERROR_MESSAGES) == set(TurnResponseErrorCode)
    assert HTTP_ERROR_MESSAGES[HttpErrorCode.AUTHENTICATION_REQUIRED] == "Authentication required"
    assert HTTP_ERROR_MESSAGES[HttpErrorCode.ORIGIN_REJECTED] == "Request origin is not allowed"
    assert HTTP_ERROR_MESSAGES[HttpErrorCode.CSRF_FAILED] == "CSRF validation failed"
    with pytest.raises(TypeError):
        HTTP_ERROR_MESSAGES[HttpErrorCode.INTERNAL_ERROR] = "untrusted replacement"


@pytest.mark.parametrize("body", [
    b'{"version":1,"version":1,"topic":"summary","claim_ids":[]}',
    b'```json\n{"version":1,"topic":"summary","claim_ids":[]}\n```',
    b'{"version":1,"topic":"summary","claim_ids":[]} extra',
    b'\xff', b" " * (MAX_PROVIDER_BYTES + 1),
])
def test_provider_wire_output_is_bounded_and_strict(body):
    with pytest.raises(GroundingContractViolation) as caught:
        parse_provider_output(body)
    assert caught.value.code == PersistedFailureCode.INVALID_PROVIDER_RESPONSE


def test_provider_body_at_exact_bound_and_no_implicit_json_coercion():
    body = b'{"version":1,"topic":"unsupported","claim_ids":[]}'
    assert parse_provider_output(body + b" " * (4096 - len(body))).topic == Topic.UNSUPPORTED
    with pytest.raises(ValidationError):
        ProviderOutput(version=1, topic=b"summary", claim_ids=[])


def test_context_local_selection_policy_and_unsupported():
    output = parse_provider_output(b'{"version":1,"topic":"budgets","claim_ids":["budget.status"]}')
    policy = {"allowed_topics": {"budget.status": frozenset({Topic.BUDGETS})},
              "required_ids": {Topic.BUDGETS: frozenset({"budget.status"})}}
    assert validate_claim_selection(output, **policy) == output
    unknown = ProviderOutput(version=1, topic="budgets", claim_ids=["unknown"])
    with pytest.raises(GroundingContractViolation) as caught:
        validate_claim_selection(unknown, **policy)
    assert caught.value.code == PersistedFailureCode.INVALID_PROVIDER_RESPONSE
    empty = ProviderOutput(version=1, topic="budgets", claim_ids=[])
    with pytest.raises(GroundingContractViolation) as caught:
        validate_claim_selection(empty, **policy)
    assert caught.value.code == PersistedFailureCode.OUTPUT_REJECTED
    unsupported = ProviderOutput(version=1, topic="unsupported", claim_ids=[])
    assert validate_claim_selection(unsupported, **policy) == unsupported
    with pytest.raises(GroundingContractViolation):
        validate_claim_selection(output, allowed_topics={"budget.status": frozenset({Topic.GOALS})},
                                 required_ids={Topic.BUDGETS: frozenset({"budget.status"})})
    selection = ProviderOutput(version=1, topic="budgets", claim_ids=["a", "b"])
    with pytest.raises(GroundingContractViolation):
        validate_claim_selection(selection, allowed_topics={key: frozenset({Topic.BUDGETS}) for key in ("a", "b")},
                                 required_ids={Topic.BUDGETS: frozenset({"a"})},
                                 exclusive_groups=(frozenset({"a", "b"}),))


class FakeProvider:
    """Test-only deterministic selection double, never imported by app code."""

    identity = ProviderIdentity(kind="fake", model="test-contract-model")

    def select_claims(self):
        return b'{"version":1,"topic":"unsupported","claim_ids":[]}'


def test_fake_provider_identity_is_explicit_and_production_selection_rejects_it():
    fake = FakeProvider()
    assert fake.identity.kind == ProviderKind.FAKE
    assert parse_provider_output(fake.select_claims()).topic == Topic.UNSUPPORTED
    assert ProviderSelection().mode == "disabled"
    for payload in ({"mode": "fake"}, {"mode": "ollama", "identity": fake.identity},
                    {"mode": "disabled", "identity": fake.identity},
                    {"mode": "fake", "test_only": True},
                    {"mode": "ollama", "identity": fake.identity.model_dump()}):
        with pytest.raises(ValidationError):
            ProviderSelection.model_validate(payload)
    with pytest.raises(ValidationError):
        ProductionProviderIdentity.model_validate(fake.identity.model_dump())


@pytest.mark.parametrize("kind", ["ollama", "llama_cpp", "hosted"])
def test_replaceable_production_selection_contract(kind):
    selected = ProviderSelection(mode=kind, identity={"kind": kind, "model": "explicit-model"})
    assert selected.identity.kind.value == kind
    for bad in ({"mode": kind}, {"mode": "disabled", "identity": selected.identity},
                {"mode": kind, "identity": {"kind": kind, "model": " "}}):
        with pytest.raises(ValidationError):
            ProviderSelection.model_validate(bad)
