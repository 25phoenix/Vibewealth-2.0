# Phase 9B — Persistent Assistant Architecture Specification

Status: canonical design contract, awaiting explicit review and approval before
Phase 9C.1. This document specifies future implementation; it does not assert
that assistant APIs, orchestration, or turn persistence already exist.

The repository uses a flat `docs/` directory (`architecture.md` and
`requirements.md`), so this document follows that convention without creating
an additional directory. For Phase 9, this specification supersedes the older
planned Gemini/tool-based assistant description in `architecture.md`; it does
not amend that document or authorize a provider subscription.

## 1. Scope and corrections incorporated

The MVP is a persistent, authenticated, financially read-only assistant. A
provider selects backend-authored claims, and the backend validates and renders
the answer. The provider cannot generate unrestricted user-visible financial
prose, perform financial writes, calculate financial facts, execute SQL, call
tools, or supply URLs. Unsupported topics receive a deterministic explanation.

The nine corrections are part of the implementation contract:

1. User-scoped idempotency uses database uniqueness recovery across conversations;
   the losing reservation never dispatches a provider call (§5).
2. Client UUID conversation creation handles primary-key races with rollback,
   ownership checks, and immutable-title replay comparison (§5).
3. `GENERATION_INTERRUPTED` is derived only from an expired pending lease, never
   stored as a turn failure (§4).
4. Submit and lookup use the same `Idempotency-Key` header; keys never appear in
   assistant URLs (§3).
5. `fake` is an explicit test-only provider identity, unavailable through normal
   application configuration (§8).
6. Abandonment is terminal, clears prior failure data, and releases the
   conversation's unresolved-turn slot (§4).
7. Idempotency and unresolved-turn checks precede generation rate/capacity
   checks; all reservation races are rechecked before dispatch (§5).
8. Dispatch and completion revalidate the original request session in short
   transactions compatible with logout's session-row update (§6).
9. Provider inference has a 45-second deadline, all work a 60-second deadline,
   and durable attempts a separate 90-second lease (§9).

No streaming, agent framework, vector database, task queue, background worker,
automatic model download, automatic cloud fallback, or paid provider is part
of this contract. Financial mutations remain exclusively in existing
authenticated domain APIs, through their normal confirmation and CSRF paths.

## 2. Verified foundation and proposed component boundaries

Source references are relative to this document. Existing behavior is distinct
from proposed behavior throughout this specification.

| Existing implementation | Source and relevant symbols | Consequence |
| --- | --- | --- |
| User-owned conversations, nullable title, timestamps, owner/id uniqueness, owner/updated index | [assistant_conversation.py](../backend/app/models/assistant_conversation.py), `AssistantConversation` | Reuse the table; do not introduce a second conversation store. |
| Ordered user/assistant messages, composite conversation-owner FK, unique conversation/sequence, positive sequence and nonempty-content checks | [assistant_message.py](../backend/app/models/assistant_message.py), `AssistantMessage` | Reuse messages; introduce durable turn state separately. |
| Session validation is conditional `UPDATE … RETURNING`; validity uses PostgreSQL wall time | [auth_sessions.py](../backend/app/services/auth_sessions.py), `get_valid_session()` | Session validation locks the row until the caller ends its transaction. |
| Revocation updates that same session row; logout commits it | [auth_sessions.py](../backend/app/services/auth_sessions.py), `revoke_session()`; [auth_routes.py](../backend/app/api/auth_routes.py), `logout()` | Short fencing transactions can serialize against logout. No inference-time lock is permitted. |
| Safe identity carries session ID; caller owns validation transaction | [authentication.py](../backend/app/services/authentication.py), `CurrentUser`, `get_current_user()` | Capture the original request's user/session identity and revalidate it at both fences. |
| Cookie authentication and trusted-origin/session-bound CSRF checks | [dependencies.py](../backend/app/api/dependencies.py), `get_authenticated_request()`, `require_csrf()` | Reuse the existing security boundary. Never accept a client owner ID. |
| INR integer-paise precision and India financial date | [financial.py](../backend/app/core/financial.py), `MAX_SAFE_PAISE`, `financial_today()` | Preserve exact money and `Asia/Kolkata` date semantics. |
| Authoritative account, budget, goal and dashboard readers | Services cited in §7 | Reuse/extract authoritative calculations rather than copying them into prompts. |
| `httpx` is already declared | [requirements.txt](../backend/requirements.txt) | Use it for provider communication; no additional SDK is required. |

Proposed layers and responsibilities:

- API routes/schemas: authentication, CSRF, strict parsing, status mapping,
  pagination, sanitized errors, `Cache-Control: no-store`.
- Conversation service: owner-scoped listing/creation/deletion and replay-safe
  UUID creation; immutable titles in this MVP.
- Turn lifecycle service: reservation, user message insertion, sequence
  allocation, idempotency, attempts, leases, retry, abandonment, and fencing.
  The turn row itself is the idempotency record; no redundant operation table.
- Shared reporting service: reusable complete financial aggregates with
  explicit user/date inputs, preserving existing domain definitions.
- Context builder: bounded immutable facts and backend-authored claim catalog;
  no mutation capability.
- Grounding validator/renderer: strict provider output validation, topic and
  claim compatibility, mandatory notices, deterministic final text.
- Orchestrator: bounded admission/context/provider/finalization workflow, with
  no database transaction spanning provider I/O.
- Provider protocol/adapters: transport only; receive neither SQLAlchemy
  sessions nor financial services nor executable operations.

## 3. HTTP API contract

### 3.1 Common rules and types

Base path: `/api/assistant`. All endpoints require the existing cookie session;
the frontend sends `credentials: 'include'`. All POST and DELETE endpoints
require trusted Origin/Referer and `X-CSRF-Token` through the existing CSRF
dependency. GET does not require CSRF. All responses, including errors, carry
`Cache-Control: no-store`. No financial data or operation keys go in query
strings. Pagination parameters are the only query parameters below.

UUID request values are canonical lowercase, hyphenated UUID strings; newly
client-generated conversation IDs and idempotency keys must be UUIDv4. Header
names are case-insensitive. `Idempotency-Key` must occur exactly once and have
exactly 36 canonical UUIDv4 characters; missing, duplicate (including
case-varied duplicates), comma-combined, malformed, or non-v4 values produce
422 `INVALID_REQUEST`. Apply identical validation to submit and lookup. Keys
are not secrets or authentication, but must still be excluded from logs.

Request bodies reject unknown fields and coercion of strings/bools into
integers. Titles are null or Unicode-trimmed, nonempty strings of at most 160
characters. Omitted title means null; empty title is invalid. Content normalizes
CRLF/CR to LF and trims outer Unicode whitespace, then must be 1–4,000 Unicode
Unicode scalar values (code points excluding surrogates) with no NUL. Reject
unpaired surrogate escapes, malformed UTF-8 and duplicate JSON object keys.
The encoded JSON request body limit is 64 KiB (65,536 bytes), enforced by bounded
reads before parsing, regardless of Content-Length. Reject non-identity request
Content-Encoding rather than accepting an unbounded decompression path.

This wire limit accommodates the maximum content even when every scalar is
encoded as a JSON surrogate pair: 4,000 × 12 ASCII bytes + 14 bytes for the
compact `{"content":""}` envelope = 48,014 bytes. Literal UTF-8 requires at
most four bytes per scalar; BMP/control escapes require at most six, and quote
or backslash escapes two. Extra insignificant JSON whitespace and whitespace
removed by normalization still count toward the wire limit; arbitrarily padded
serializations need not be accepted. Validate the normalized 4,000-scalar bound
separately after bounded parsing. This wire allowance does not increase model
context/history/output budgets. Dates are ISO date-only; timestamps are UTC RFC3339.

Pagination is `{items, total, offset, limit}` with offset default 0, nonnegative
integer, and limit default 50, integer 1–100. Total counts all matching owned
records, independent of the selected page. Empty/out-of-range pages are 200
with an empty items array. Offset pagination is intentionally not a stable
snapshot while conversations change; clients deduplicate by ID.

Response definitions (all listed fields required; nullable fields use null):

```text
ConversationDto = {
  id: UUID, title: string|null, created_at: timestamp, updated_at: timestamp,
  last_sequence_no: integer>=0, unresolved_turn: TurnDto|null
}
MessageDto = {
  id: UUID, conversation_id: UUID, sequence_no: integer>0,
  role: "user"|"assistant", content: string, created_at: timestamp,
  turn: {id: UUID, status: TurnStatus, attempt_no: integer}|null
}
TurnStatus = "pending"|"completed"|"failed"|"abandoned"
TurnDto = {
  id: UUID, conversation_id: UUID, idempotency_key: UUID,
  status: TurnStatus, attempt_no: integer[1,3],
  user_message: MessageDto, assistant_message: MessageDto|null,
  created_at: timestamp, attempt_started_at: timestamp,
  attempt_finished_at: timestamp|null, lease_expires_at: timestamp|null,
  context_as_of: timestamp|null, financial_date: date|null,
  lease_expired: boolean, can_retry: boolean, can_abandon: boolean,
  error: {code: TurnResponseErrorCode, message: string}|null
}
ErrorDto = {
  detail: string, code: HttpErrorCode,
  issues: [{location: string, message: string}],
  current_turn: TurnDto|null
}
```

Message metadata is shallow, never recursively embeds TurnDto. Legacy messages
without a turn have `turn: null`. TurnDto always includes the same persisted
user message across attempts. Provider identifiers, raw output, fingerprints,
and session IDs are internal and absent from these DTOs. An unresolved turn is
pending or failed, including nonretryable failed; completed/abandoned are not
unresolved. `last_sequence_no` is the greatest persisted message sequence (0
if none), not a turn's reserved but unused reply sequence.

### 3.2 Endpoint summary

| Method and path | Request / extra headers | Success and replay behavior |
| --- | --- | --- |
| POST `/conversations` | `{id: UUIDv4, title?: string|null}`; CSRF | 201 new ConversationDto; 200 matching immutable-create replay. No Idempotency-Key: UUID is the creation key. |
| GET `/conversations` | offset, limit | 200 page of ConversationDto; order `updated_at DESC, id DESC`. |
| GET `/conversations/{conversation_id}` | None | 200 ConversationDto, including unresolved turn for recovery. |
| DELETE `/conversations/{conversation_id}` | CSRF, no body | 204 empty; hard-deletes conversation, messages and turns atomically. Unknown/foreign ID: 404, including a repeated DELETE. |
| GET `/conversations/{conversation_id}/messages` | offset, limit | 200 message page ordered `sequence_no ASC`. |
| POST `/conversations/{conversation_id}/messages` | `{content: string}`; CSRF; `Idempotency-Key` | Synchronous owner attempt; 201 TurnDto when this request reserved the new turn and finalized it (completed or failed). Matching replay returns 200 if resolved or interrupted, 202 if still pending with live lease. |
| GET `/turns/by-key` | `Idempotency-Key`; no key in URL | 200 current TurnDto or 404 `TURN_NOT_FOUND`. Lookup never dispatches or mutates turn state. |
| GET `/conversations/{conversation_id}/turns/{turn_id}` | None | 200 TurnDto in every found lifecycle state, including pending. |
| POST `/conversations/{conversation_id}/turns/{turn_id}/retry` | `{expected_attempt_no: integer[1,3]}`; CSRF | 200 TurnDto for a newly claimed retry finalized as either completed or failed, or resolved/derived-interrupted replay; 202 live pending replay. New attempt is synchronous, not queued. |
| POST `/conversations/{conversation_id}/turns/{turn_id}/abandon` | `{expected_attempt_no: integer[1,3]}`; CSRF | 200 abandoned TurnDto, including exact repeated abandonment. |

202 includes `Retry-After: 2`; it promises durable pending state, not a background
job. Only the request that commits a new attempt owns its execution. A matching
duplicate, GET, or polling request never resumes inference. If the owning
request dies, explicit retry after lease expiry is necessary. A new submit
whose generation fails still returns a persisted failed TurnDto rather than
pretending the user message was not accepted. Authentication loss is always
401 without a successful generated answer, even if a turn was already reserved.

### 3.3 Error semantics

HTTP admission/protocol errors use ErrorDto; `issues` is empty unless validation
needs safe field-level detail. Never echo content, cookies, keys or raw provider
errors. Existing auth/CSRF detail strings remain compatible with the current
client (`Authentication required`, `Request origin is not allowed`,
`CSRF validation failed`). `current_turn` is nonnull only for authorized
unresolved/attempt/lifecycle conflicts; never disclose a foreign operation.

| HTTP | Codes | Meaning |
| --- | --- | --- |
| 401 | `AUTHENTICATION_REQUIRED` | Missing, expired or revoked original session; no generated success body. |
| 403 | `ORIGIN_REJECTED`, `CSRF_FAILED` | Existing trusted-origin/CSRF protection failed. |
| 404 | `CONVERSATION_NOT_FOUND`, `TURN_NOT_FOUND` | Absent or foreign-owned resources, including UUID-create foreign collision. |
| 404 | `ASSISTANT_ROUTE_NOT_FOUND` | Unmatched application paths under `/api/assistant`; fixed detail `Assistant route not found.`. |
| 405 | `METHOD_NOT_ALLOWED` | Unsupported methods on a matched assistant path; fixed detail `Method not allowed.`; preserve the framework's `Allow` header. |
| 409 | `CONVERSATION_CREATE_CONFLICT`, `IDEMPOTENCY_CONFLICT` | Immutable creation attributes or canonical submission fingerprint differ. |
| 409 | `UNRESOLVED_TURN`, `ATTEMPT_CONFLICT`, `TURN_NOT_RETRYABLE`, `TURN_NOT_ABANDONABLE`, `RETRY_LIMIT_REACHED` | Lifecycle admission refused; current owned turn included where applicable. |
| 409 | `CONVERSATION_LIMIT_REACHED`, `TURN_LIMIT_REACHED` | Persistence bounds reached; no new accepted operation. |
| 413 / 422 | `REQUEST_TOO_LARGE` / `INVALID_REQUEST` | Body bound or strict header/body/path/pagination validation failed. |
| 429 | `RATE_LIMITED`, `GENERATION_BUSY` | New execution admission refused; Retry-After supplied. Replays/unresolved resolution precede capacity. |
| 503 | `PROVIDER_DISABLED`, `PROVIDER_CONFIGURATION_INVALID`, `DATABASE_UNAVAILABLE`, `WORK_DEADLINE_EXCEEDED` | No configured provider, invalid configuration, database unavailable, or no timely finalization. An already-reserved operation must be recovered, never assumed absent. |
| 500 | `INTERNAL_ERROR` | Sanitized unexpected failure; ambiguous writes require lookup. |

Phase 9C.3 additive contract refinement: application-level router 404/405 errors
under `/api/assistant` also use ErrorDto and `Cache-Control: no-store`. These two
codes do not replace resource-level `CONVERSATION_NOT_FOUND` or `TURN_NOT_FOUND`.
Normal non-assistant framework errors and CORS preflight semantics are unchanged.

TurnDto.error is a lifecycle report, distinct from HTTP errors. Persisted failure
codes and retry eligibility are specified in §4. A 200/201 failed TurnDto is not
a successful financial answer. The frontend must check `status`, not only HTTP.

## 4. State machine and lifecycle response projection

### 4.1 Persisted states versus response-only conditions

| Persisted state / condition | TurnDto projection | Allowed next action |
| --- | --- | --- |
| pending, PostgreSQL time < lease expiry | error null; lease_expired false; can_retry false; can_abandon false | Owning attempt may complete/fail; other requests poll or delete conversation. |
| pending, PostgreSQL time >= lease expiry | status stays pending; error `GENERATION_INTERRUPTED`; lease_expired true; can_retry iff attempt_no < 3; can_abandon true | Explicit retry or abandon; GET does not rewrite persistence. |
| completed | assistant message present; error null; lease_expired false; can_retry/can_abandon false | New turn or delete conversation. |
| failed with retryable persisted code | assistant null; error is persisted code; lease_expired false; can_retry iff attempt_no < 3; can_abandon true | Explicit retry or abandon. |
| failed with nonretryable persisted code | assistant null; error is persisted code; can_retry false; can_abandon true | Abandon before a new turn, or delete conversation. |
| abandoned | assistant null; error null; lease null; lease_expired false; can_retry/can_abandon false | New turn or delete conversation; repeated exact abandon returns current state. |

`GENERATION_INTERRUPTED` is in TurnResponseErrorCode only. It is not a database
failure code, not a fifth status, not persisted by polling, and not a claim
about the provider's actual completion. It means an attempt has no valid lease
and no committed final result. Lease-expired stale responses cannot finalize.

PersistedFailureCode and retry policy:

| Code | Retryable (subject to attempt limit) |
| --- | --- |
| `PROVIDER_TIMEOUT` | Yes |
| `PROVIDER_UNAVAILABLE` | Yes |
| `PROVIDER_RATE_LIMITED` | Yes |
| `INVALID_PROVIDER_RESPONSE` | Yes |
| `CONTEXT_UNAVAILABLE` | Yes |
| `SESSION_INVALIDATED` | Yes, only after valid reauthentication |
| `INTERNAL_FAILURE` | Yes |
| `CONTEXT_LIMIT` | No |
| `FINANCIAL_INVARIANT` | No |
| `OUTPUT_REJECTED` | No |

TurnResponseErrorCode is exactly PersistedFailureCode plus
`GENERATION_INTERRUPTED`. HTTP codes are a separate enum. Provider transport
timeout is persisted as `PROVIDER_TIMEOUT` if finalization can commit in time;
expired pending is interruption regardless of the unknown original cause.

### 4.2 Transitions and attempts

```text
new reservation -> pending(attempt=1)
pending(live lease, matching attempt) -> completed | failed
pending(expired lease, attempt<3) -> pending(attempt+1) via explicit retry
failed(retryable, attempt<3) -> pending(attempt+1) via explicit retry
failed(any) | pending(expired lease) -> abandoned via explicit abandon
any state -> removed by conversation deletion
completed and abandoned -> no further execution of this turn
```

There is one unresolved turn per conversation, even when failed/nonretryable or
expired. Retry reuses its user message, key and fingerprint; no duplicate user
message. It increments attempt_no, sets a new lease and attempt-start time,
clears finish/error/context fields, and records the selected provider/model for
the current attempt. This removes the derived interrupted condition immediately
on commit. At most three reserved attempts total; rejected admission does not
consume an attempt. Attempt limit includes interrupted attempts. Exhausted
pending/failed turns remain unresolved until abandonment or deletion.

Abandonment sets status abandoned, clears lease and error_code, sets
attempt_finished_at to abandonment time, and retains the user message, attempt
number, current attempt provider identity and any existing context metadata.
Prior failure_code is deliberately **not preserved** in the turn row: this MVP
does not add a diagnostic attempt log. Sanitized bounded operational events may
record the prior code without financial content. Abandoned state is described
by status and finish time, never a retryable failure code. The frontend labels
it abandoned, preserves its user message, and permits a new turn.

Retry/abandon use compare-and-set `expected_attempt_no`. If current attempt is
less than expected: 409 ATTEMPT_CONFLICT. A retry with current greater than
expected returns current lifecycle without executing (the earlier retry may
have succeeded). With equal attempt: completed returns 200 unchanged; abandoned
retry is 409 TURN_NOT_RETRYABLE; live pending retry returns 202 unchanged;
otherwise claim only if retryable and below max, or return the specific 409.
Abandon with greater current attempt is 409 ATTEMPT_CONFLICT (never abandon a
newer retry); equal abandoned is 200; completed/live pending is 409
TURN_NOT_ABANDONABLE. Exact repeated abandon therefore cannot revive a turn.

## 5. Persistence, idempotency and admission

### 5.1 AssistantTurn schema

A separate table is necessary: messages alone cannot atomically represent a
request key, pending lease, attempt fencing, failed generation without reply,
or abandonment. Do not create a second idempotency table, store raw provider
responses, persist context snapshots, or create an attempt-history table.

All fields below are proposed, not existing columns. PostgreSQL types are
normative; Python/SQLAlchemy equivalents must retain these constraints.

| Field | Type / nullability | Purpose and constraints |
| --- | --- | --- |
| id | UUID, required, PK | Server-generated turn identity. |
| user_id | UUID, required | Owner; authenticated server value, never client supplied. |
| conversation_id | UUID, required | Composite owner FK to conversation, ON DELETE CASCADE. |
| idempotency_key | UUID, required | Unique with user_id across all conversations. Application enforces UUIDv4. |
| request_fingerprint | BYTEA, required, length 32 | SHA-256 of canonical request described below; immutable. |
| user_sequence_no | INTEGER, required, 1..2147483646 | References persisted user message; unique per conversation. |
| assistant_sequence_no | INTEGER, nullable | Present only for completed; must equal user_sequence_no+1. |
| status | VARCHAR(16), required | pending/completed/failed/abandoned; check constraint. |
| attempt_no | SMALLINT, required, 1..3 | Monotonically increasing fencing token for current attempt. |
| created_at | TIMESTAMPTZ, required | Turn reservation time; immutable across retry. |
| attempt_started_at | TIMESTAMPTZ, required | Start of latest reserved attempt. |
| attempt_finished_at | TIMESTAMPTZ, nullable | Completion/failure/abandonment time; null while pending. |
| lease_expires_at | TIMESTAMPTZ, nullable | Pending attempt's start + 90 seconds using PostgreSQL wall time. |
| context_as_of | TIMESTAMPTZ, nullable | Database observation time sampled by the snapshot-establishing statement (§7.1), not an exact commit cutoff. |
| financial_date | DATE, nullable | context_as_of observation time converted to Asia/Kolkata date; paired with context_as_of. |
| provider_kind | VARCHAR(16), required | Current attempt: ollama, llama_cpp, hosted, or explicit test-only fake. Disabled is not an executing identity. |
| model_name | VARCHAR(160), required | Nonblank, bounded configured model identifier; not chosen by user. |
| contract_version | SMALLINT, required, equals 1 | Grounding contract version used by attempt. |
| error_code | VARCHAR(40), nullable | PersistedFailureCode only; populated exactly when failed. |

Database constraints/indexes:

- Named `uq_assistant_turns_user_key` UNIQUE(user_id, idempotency_key).
- Composite FK(user_id, conversation_id) references
  assistant_conversations(user_id, id), ON DELETE CASCADE; this is the ownership
  guarantee for every turn. Existing messages already have their owner FK.
- UNIQUE(conversation_id, user_sequence_no), and FK(conversation_id,
  user_sequence_no) to assistant_messages(conversation_id, sequence_no).
  ON DELETE CASCADE is compatible with conversation cascade.
- Nullable composite FK(conversation_id, assistant_sequence_no) to messages,
  DEFERRABLE INITIALLY DEFERRED, NO ACTION, allowing atomic reply insertion and
  conversation deletion. Application verifies matching owner and message role;
  cross-table role assertions cannot be ordinary CHECK constraints.
- Named partial unique index `uq_assistant_turns_unresolved_conversation` on
  (conversation_id) WHERE status IN ('pending','failed') enforces
  one unresolved turn. Do not add redundant user/key, conversation/user-message,
  or unresolved-turn indexes already covered by these constraints. No lease
  scan index or sweeper is required for the explicit-recovery MVP.
- Checks for enums, fingerprint length, sequence relation/range, attempts,
  contract version, nonblank model, context pair both null or both nonnull,
  created_at <= attempt_started_at and finish/context times not before start.
- State checks: pending => reply null, lease nonnull and greater than start,
  finish null, error null; completed => reply nonnull, lease null, finish
  nonnull, error null, context pair nonnull; failed => reply null, lease null,
  finish nonnull, error in persisted enum; abandoned => reply null, lease null,
  finish nonnull, error null. Context pair may remain on failed/abandoned.

Do not add message content backfill or fabricate legacy turns. Legacy messages
remain readable with null turn metadata. Future migration must register the
model, create named constraints and test upgrade/downgrade in isolated test
schemas. Validate actual Alembic head before authoring that future migration;
no database revision was queried for this documentation task.

### 5.2 Sequence and persistence boundaries

All authenticated writes use short transactions with this global lock order:
authentication session -> owner User row (only when needed for conversation
capacity) -> conversation -> turn. Skip locks that an operation does not need;
never acquire an earlier lock while holding a later one. Creation takes session
then User before capacity counting/insertion; ordinary turn operations, deletion
and finalization take session then conversation then turn, without a User lock.
If multiple rows of one class are ever needed, lock them in ascending UUID order.
Collision recovery rolls back all locks and restarts in this order; it must not
upgrade a conversation-held transaction to acquire User or session locks. No
assistant operation acquires multiple session rows. Apply the same order to
future assistant endpoints; account-deletion or other future cross-domain lock
changes require explicit deadlock review rather than an inverted acquisition.
The narrowly authorized invalid-session cleanup exception is defined in §6.1.

Reservation locks the owned
conversation, checks limits/unresolved state, inserts the user message and turn
atomically, and updates conversation.updated_at. Determine next user sequence
above both the maximum persisted message and every prior reserved reply
position (user_sequence_no+1). Reserve the following sequence for the assistant;
gaps from abandonment are allowed and never reused. Retries do not allocate
sequences. Completion inserts one reply and updates turn/conversation in one
transaction; failed attempts insert no assistant message.

Conversation capacity is 100 per user; 1,000 turns per conversation (including
abandoned/completed), plus integer sequence overflow guard. The user limit
requires a short owner User-row lock for conversation creation after session
validation, before inserting; a replay is resolved before capacity enforcement.
No financial rows are locked or mutated by assistant operations.

### 5.3 Canonical idempotency and uniqueness recovery

The fingerprint is the 32-byte SHA-256 of one exact canonical serialization,
not of the received JSON body. Build only the three fields below after request
validation/normalization, then serialize in lexicographic key order (`content`,
`conversation_id`, `version`), with no insignificant whitespace, no BOM and no
trailing newline:

```json
{"content":"<normalized content>","conversation_id":"<canonical UUID>","version":1}
```

Encode as UTF-8 without ASCII-escaping non-ASCII scalars. Escape quote and
backslash as `\"` and `\\`; use `\b`, `\f`, `\n`, `\r`, `\t` for their control
characters and lowercase `\u00xx` for remaining U+0000–U+001F characters
(NUL remains forbidden input). Do not escape `/`, U+2028 or U+2029, perform
Unicode NFC/NFKC normalization, or change interior whitespace. Version is the
JSON integer `1`, UUID is the validated lowercase canonical string. The
normative reference serialization is Python
`json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
allow_nan=False).encode('utf-8')` after these validations. Equivalent
implementations must produce the same bytes; default serializer settings are
not sufficient.

Concrete golden vector (the raw-content line below is JSON notation, with
escapes representing characters in the decoded input):

```text
conversation_id: 123e4567-e89b-42d3-a456-426614174000
raw content: " \r\nShow ₹100 \"budget\".\r\n "
normalized content: Show ₹100 "budget".
canonical UTF-8 text (one line; no final newline):
{"content":"Show ₹100 \"budget\".","conversation_id":"123e4567-e89b-42d3-a456-426614174000","version":1}
UTF-8 byte length: 106
SHA-256 hex: 2570b775ad4bf225cf7c39bfa536ceb5d0f181bd8143f3982eaecfe2e26d1f99
```

Contract tests must assert these literal canonical bytes and digest rather
than computing their expected value with the implementation under test. Add
vectors for control escaping, non-BMP characters, combining characters kept
distinct, key ordering and newline/outer-whitespace normalization.

Keys are user-wide, not conversation-wide. The conversation ID is in the
fingerprint, so the same key submitted to different conversations necessarily
conflicts, even for identical text. Provider settings/history/context are not
part of the fingerprint. A matching retry refers to the original operation,
not a new snapshot or implicitly new generation.

Resolve `(authenticated_user_id, key)` before generation admission. Matching
fingerprint returns the existing lifecycle (§3/§4); differing fingerprint is
409 IDEMPOTENCY_CONFLICT. Do not reveal an operation belonging to another user.
Retention is until conversation deletion; no tombstone is introduced. Deletion
removes replay protection for its keys, so the client must never reuse a key
for a new operation or automatically resubmit a deleted operation.

Required cross-conversation race handling:

1. Attempt the short atomic reservation (user message plus turn/idempotency row).
2. If and only if PostgreSQL rejects the relevant named user/key uniqueness
   constraint (SQLSTATE 23505), roll back the entire failed transaction.
3. In a fresh transaction, revalidate authentication and query by (user_id, key).
4. Compare the stored canonical fingerprint.
5. Matching: return the existing operation's current lifecycle; no execution.
6. Different: return 409 IDEMPOTENCY_CONFLICT; no execution.
7. The loser must never call the provider. Unrelated integrity errors are not
   idempotent replays and must not be swallowed.

Conversation locks do not serialize different conversations; session locks do
not serialize different sessions of the same user. Database uniqueness is the
final authority across workers/sessions. If the winning record is concurrently
deleted before recovery lookup, return non-disclosing 404 TURN_NOT_FOUND with
no provider invocation; do not restart reservation internally.

### 5.4 Conversation UUID creation race

The client generates one UUIDv4 and retains the exact normalized creation
payload until resolved. Ownership and normalized original title (null if
omitted) are immutable creation attributes. There is no rename endpoint in
this MVP; a future rename feature must preserve original creation attributes
separately before enabling replay with mutable titles.

On `pk_assistant_conversations` conflict: roll back, open a fresh authenticated
transaction and query the UUID for the narrowly scoped collision check. If
owned and immutable creation attributes match: 200 replay. Owned but title or
other immutable creation attributes differ: 409 CONVERSATION_CREATE_CONFLICT.
Foreign-owned or disappeared: 404 CONVERSATION_NOT_FOUND. Never disclose foreign
title/owner, overwrite the winner, or treat an unrelated constraint error as
creation replay. This exceptional collision lookup must not leak into ordinary
owner-scoped resource access.

### 5.5 Admission and dispatch ordering

The ordering is normative for submit and explicit retry:

1. Validate authenticated session, trusted origin/CSRF where required, and bounded
   request/header syntax. Resolve owned conversation/turn.
2. Resolve idempotency replay/conflict (or retry's expected-attempt replay).
   Resolved/pending existing operation returns its lifecycle without provider
   capacity checks or generation-start quota consumption.
3. Check unresolved-turn admission under the conversation lock. A new distinct
   operation blocked by an existing pending/failed turn returns 409
   UNRESOLVED_TURN and its current TurnDto, including derived interruption when
   applicable. It must not return GENERATION_BUSY instead. Completed/abandoned
   turns do not block. Retry addresses the unresolved turn itself.
4. End this short transaction before waiting on anything external. Atomically
   reserve a provisional new-generation quota entry, validate provider
   enabled/configuration state, then perform an atomic non-queuing capacity
   try-acquire. The try-acquire checks and increments global and per-user
   execution counters together, all-or-nothing, returning one owned token or
   immediate refusal. A separate capacity check followed by acquisition is
   prohibited; do not await a semaphore slot. Limiter critical sections are
   process-local, bounded and contain no await/I/O/database work. If refused,
   refund any provisional quota entry and repeat the
   idempotency/unresolved lookup before emitting the refusal, since another
   request may have reserved in the meantime. This is a bounded recheck, not
   an automatic generation retry.
5. After successful try-acquire, open a new short reservation transaction, with
   session -> conversation -> turn lock ordering. Recheck key/fingerprint,
   attempt/unresolved state, limits and ownership. Reserve atomically or apply
   the named constraint-recovery rules. Only the reservation owner proceeds;
   every losing/replay/refusal path releases capacity.
6. Commit before context/provider work. Construct context, perform the dispatch
   fence (§6), then invoke the provider exactly once for this claimed attempt.

If the named unresolved-turn unique index nevertheless rejects reservation,
roll back, revalidate in a fresh transaction, resolve the user/key first, then
query the owned unresolved turn and return its lifecycle/conflict as above.
Do not misclassify this constraint as a user/key replay or a capacity error.
If the blocking turn disappeared or resolved before recovery, return 409
ATTEMPT_CONFLICT with current_turn null and require a fresh client decision;
the losing request still never dispatches. Normal conversation locking should
avoid this branch, but the database constraint remains a defensive boundary.

Rate admissions and capacity tokens are process-local operational controls,
not durable correctness boundaries. A provisional quota entry counts against
the eight-start limit while held, so concurrent provisional admissions cannot
oversubscribe it. Immediately before entering the provider adapter, atomically
commit that entry as a generation start timestamp. Refund it exactly once if
execution never reaches adapter invocation, including context/fence failure,
disabled provider, reservation loss, replay, refusal, cancellation or cleanup
before dispatch. Once invocation starts, retain the quota event even if the
provider rejects/fails or the client disconnects; do not refund real attempts.
This operational quota is distinct from the durable attempt counter: a
committed turn reservation consumes an attempt even if subsequent pre-dispatch
work fails, whereas a reservation rolled back or never committed consumes none.

Capacity-token ownership begins at successful try-acquire and is protected by
one outer finally/cleanup owner covering reservation, context, dispatch and
finalization. Release exactly once on reservation loss, replay, refusal,
provider success/failure, parsing/finalization failure, cancellation and request
cleanup. If provider transport was started, close/cancel and join that bounded
transport task before releasing; if not, release immediately on exit. Nested
handlers must not double-release or bypass this owner. Cleanup obeys the same
overall deadline (§9), not a detached task. Process termination destroys these
process-local tokens; restart does not inherit capacity reservations. Retry
does not bypass key checks, session checks or max_attempts. No replay, read, or
uniqueness-loser path dispatches a provider.

## 6. Session fencing, deletion, and result ownership

### 6.1 Verified locking and required strategy

`get_valid_session()` uses conditional UPDATE on AuthSession with revocation,
idle-expiry and absolute-expiry predicates and PostgreSQL `clock_timestamp()`.
It holds the row lock until transaction end. `revoke_session()` updates that
same row; `logout()` commits. These operations have compatible serialization
when the assistant explicitly controls transaction boundaries. Do not assume
an old dependency result or cached ORM object is a fresh validity check.

At request admission capture the authenticated user ID, session ID and internal
cookie token in memory only. Before inference and before result persistence,
use a fresh short READ COMMITTED transaction and the existing validation
operation (or a shared equivalent with exactly the same predicates), verify
the resolved user/session IDs equal the captured IDs, then lock conversation
and turn and check ownership/status/attempt/lease. A different session acquired
during the request cannot silently replace the captured one. A later explicit
retry may be authorized by another valid session of the same user.

Dispatch fence:

1. After context construction, revalidate and lock the original session.
2. Lock owned conversation and turn; require pending, captured attempt number,
   live lease, and work deadline remaining. Persist context_as_of/financial_date.
3. Commit and release all DB connections/locks before provider I/O.
4. Dispatch only for this attempt. Logout may commit immediately after this
   fence; preventing all post-revocation dispatch would require a different
   coordination mechanism and is not claimed here.

Completion fence:

1. Parse/validate selection and render in memory, within work deadline.
2. In a new transaction, revalidate original session and matching IDs first,
   then lock owned conversation and turn.
3. Require pending, exact captured attempt_no, unexpired lease according to
   PostgreSQL time, and time remaining to commit. Insert the backend-rendered
   reply, set completed and finish time, clear lease, update conversation.
4. Commit before returning a successful answer. A stale attempt, removed
   conversation, or invalid original session cannot persist a generated reply.

Failure finalization also fences by conversation/turn ownership, exact pending
attempt and live lease, without overwriting a newer attempt. If session became
invalid, return 401 without generated content; within the remaining deadline,
an internal cleanup transaction may mark only the already-captured owned turn
failed SESSION_INVALIDATED. This is an internal capability of the execution
owner for an operation whose reservation already committed while authenticated,
not an endpoint or general unauthenticated write mechanism. It uses only the
captured user_id, conversation_id, turn_id and attempt_no, never IDs supplied
by a new unauthenticated request. It locks conversation then turn (no later
session/User-lock acquisition), requires the captured owner and pending exact
attempt with live lease, and conditionally updates only failure status, finish
time, lease and error code. It cannot alter message/context/identity content,
revive deleted rows, overwrite a retry or abandoned turn, or affect other turns.
That cleanup is not an authenticated read or result publication, and must not
refresh a revoked session, create a new operation, or insert an assistant
message. If cleanup cannot finish safely, leave pending for
lease-based recovery. Authentication dependency transactions must be explicitly
committed/rolled back before reporting/context/inference; do not accidentally
keep the dependency's UPDATE lock across the whole request.

### 6.2 Ordering guarantees and limits

- If logout commits before the completion fence acquires the session row, the
  revalidation fails: no generated successful result is persisted or returned.
- If completion owns the session lock and commits first, logout waits and may
  revoke afterward. That result may already be persisted or in transit; logout
  cannot retract it. No claim of instantaneous cancellation is made.
- Inference already running may continue after revocation. Cancel best-effort
  on detected invalidation/disconnect, but assume cancellation may not stop
  model execution. The completion fence prevents later publication when logout
  won. Previously dispatched context cannot be recalled.
- PostgreSQL predicates use wall time, not transaction-start `now()` for lease
  checks. Short bounded transactions minimize expiry-boundary windows; this
  defines validity at the final fenced validation, not at eventual byte receipt.
- Frontend session-generation isolation must ignore all responses from older
  sessions, including a response committed just before logout.

Conversation DELETE uses the same short session-first fencing and an owned
conversation lock. It may delete during inference without waiting for inference.
Cascade removes turns/messages and therefore invalidates all pending attempts.
If delete commits first, late finalization returns 404 without recreating rows.
If completion commits first, deletion subsequently removes that result. No
provider response may resurrect a conversation. A delete network failure is
reconciled by GET; it must not cause automatic new submission of deleted turns.

## 7. Financial context and reporting contract

### 7.1 Snapshot and authoritative facts

Use one short, tenant-scoped REPEATABLE READ, READ ONLY financial-reporting
transaction, separate from the already-committed auth/turn writes, on a fresh
connection/transaction with those characteristics set before its first query.
Its first snapshot-taking statement is
`SELECT pg_current_snapshot() AS snapshot_id, clock_timestamp() AS observed_at`.
PostgreSQL establishes the repeatable-read MVCC snapshot for that statement;
the database clock sample is taken during the statement, after snapshot
acquisition, and its observed_at is the sole `context_as_of` value. Subsequent
financial queries reuse that same transaction/snapshot. Do not allow an earlier
ORM/autobegin query to establish another snapshot; transaction setup statements
are not financial reads. snapshot_id may remain in memory for verification but
does not require a persisted column or logging.

`context_as_of` means database observation time for the established snapshot,
not an exact wall-clock commit cutoff or the application request-start time.
A commit between snapshot acquisition and the clock sample can be absent even
though its timestamp precedes observed_at. Render 'Observed at … from a
consistent database snapshot', not 'includes every commit through …'. Do not
claim PostgreSQL exposes an exact snapshot-acquisition timestamp through this
clock sample. Derive financial_date solely from observed_at in Asia/Kolkata
and pass it explicitly to every reader, including across a midnight boundary.
This observation-date rule does not change any financial inclusion definitions.
All readers take that date explicitly; existing helpers that
call `financial_today()` internally require a shared optional as_of/reporting
refactor before use. Never silently mix midnight dates or independently
committed snapshots. Commit/close the read transaction before provider I/O.

| Fact | Authority / required sharing | Exact semantics |
| --- | --- | --- |
| Active accounts and per-account actual balance | [accounts.py](../backend/app/services/accounts.py), `get_account_balance()`, `_account_balance_query()` | Opening balance plus nondeleted income minus nondeleted expense on/after opening_balance_as_of and through financial_date inclusive. Active list excludes archived accounts. A date before opening is unavailable, not zero. |
| Account allocations and available-to-spend | Same account snapshot query | Net contribution-minus-withdrawal ledger effective_date <= financial_date, including compensating deletion withdrawals. Available = actual balance minus allocation exactly once. Aggregate active-account totals use that same scope; never subtract goal totals again. |
| Month cash flow | [dashboard.py](../backend/app/services/dashboard.py), `get_dashboard_summary()`, `_SUMMARY_SQL`, `dashboard_month_range()` | Nondeleted transactions within [month_start,next_month), <= financial_date and >= each account's opening date, including owned archived accounts. Income, expenses, and net income-minus-expenses are separate; net is cash flow, not allocated savings. |
| Monthly budgets | [budgets.py](../backend/app/services/budgets.py), `list_budgets()`, `_load_snapshots()`, `BudgetSnapshot`; dashboard budget aggregates | Full calendar [month_start,next_month) nondeleted expenses, with NO account-opening-date or today cutoff. Overall includes uncategorized expenses; category budget only its category. Income/goal entries excluded. Remaining may be negative; basis points use authoritative integer half-up rounding. Archived-category history retained. |
| Active goals, targets, target dates, descriptions, allocation by account, remaining target | [goals.py](../backend/app/services/goals.py), `list_goals()`, `get_goal()`, `_allocations_by_goal_and_account()` | Active goals; ledger net through financial_date. Allocations are virtual reservations, not expenses or transfers and do not change actual balance. Target can be exceeded; remaining_target can be negative. Goal deletion's release semantics in `delete_goal()` remain unchanged. |
| Recent transactions | [dashboard.py](../backend/app/services/dashboard.py), recent-transaction selection in `_SUMMARY_SQL` | Reuse the dashboard's authoritative inclusion and deterministic date/creation/ID ordering; a bounded subset is not complete spending history. Exclude free-text descriptions from model input by default. |
| Historical category comparison | New shared reporting service required in 9D | Complete grouped nondeleted expense aggregates, union of categories in both periods including uncategorized and archived categories. Use budget-spending inclusion rules, explicitly label these as recorded expenses rather than dashboard cash flow. Never sum a page or a dashboard top-N subset. |

Historical default: current month-to-financial_date inclusive versus previous
month start through the same day number, clamped to that month's final day.
Represent intervals internally as [start,end_exclusive), render actual dates,
and disclose unequal day counts. Backend computes current/prior paise and
signed delta; positive prior permits integer half-up percentage/basis points.
Prior zero => no percentage, with deterministic 'no prior spending' language;
both zero => no activity. Rank complete aggregates before selecting top five
categories or top five positive increases, with stable category-ID tie-breaks.
Do not infer causes, missing purchases, or a trend from a single transaction.

The shared reporting service must extract/reuse authoritative selectors and
calculations and be covered against domain service outputs; duplicating SQL
definitions in an assistant-only implementation is prohibited. Refactors must
preserve financial API behavior and the deliberate cash-flow/budget difference.

### 7.2 Completeness, money, and bounded context

Context is an immutable typed value with version, snapshot observation timestamp, financial
date, explicit intervals, facts, completeness/coverage flags and claim catalog.
All money stays integer paise internally; potentially unbounded aggregates
serialize as exact signed decimal strings. No floating-point financial math;
backend formatting owns INR text and percentages. Individual domain safe-range
constraints remain unchanged. Negative invariant violations fail closed as
FINANCIAL_INVARIANT; legitimate negative remaining budgets/goals are allowed.

No accounts/budgets/goals/transactions are separate facts, not provider errors.
No budget does not mean unlimited spending. Unknown recurring obligations,
future income, missing imports or incomplete record keeping mean affordability
cannot be guaranteed. A successful query with zero rows differs from a failed
query. Snapshot/section truncation is explicit; total aggregates remain complete
even when item lists are capped. If a required section cannot load, do not
fabricate it or substitute zeros; use CONTEXT_UNAVAILABLE or a deterministic
missing-data claim when that claim accurately describes the available context.

Limits: 10 account details, 10 current-month budget details, 10 goal details,
10 recent transactions, top five category totals and top five positive category
increases; total claim catalog at most 64. Include complete counts/totals and
mandatory truncation notices. Conversation context is at most six completed
user/assistant pairs plus the current user message; abandoned/failed turns do
not become financial evidence. Historic assistant replies are untrusted stale
text, never current facts.

Total model context budget is 16,384 tokens including instructions, catalog,
history, current input and reserved output. The selected adapter/model must
have a benchmark-verified token accounting method and actual context support.
Do not assume a universal chars-to-tokens ratio. Drop oldest history first,
then optional detail claims; retain required topic baselines, timestamps and
limitations. If still too large or counting cannot be trusted, CONTEXT_LIMIT;
never silently truncate mandatory context. Exact tokenizer/counting support is
a benchmark gate (§12), not permission to install a dependency automatically.

## 8. Grounding and provider contracts

### 8.1 Enforceable selection and rendering

Provider output is one JSON object and nothing else:

```json
{"version":1,"topic":"budgets","claim_ids":["budget.overall.status"]}
```

Exact keys: version (strict integer 1), topic (enum below), claim_ids (array of
0–12 unique ASCII claim IDs, each 1–80 characters). Reject extra keys, duplicate
JSON keys, trailing prose, markdown fences, money fields, expressions, nested
objects, invalid encoding, unknown IDs or malformed schema. Maximum provider
body is 4 KiB and generation cap 512 tokens. Do not attempt permissive extraction
of a JSON fragment from prose or automatically reprompt for repair.

Topics: summary, accounts, cash_flow, spending, budgets, goals,
category_comparison, recent_transactions, affordability_context, unsupported.
Each claim is a complete backend-authored template with typed authoritative
arguments, topic allowlist, coverage requirements and deterministic ordering.
The provider selects whole claims; it cannot supply an amount, entity name,
date, percentage, comparison, recommendation, argument or template string.

Backend validation verifies schema, context-local claim membership, topic
compatibility, mutual-exclusion rules and required topic baseline claims. The
renderer adds mandatory snapshot, missing-data, truncation and affordability
limitations independently of provider selection. Incorrect schema is
INVALID_PROVIDER_RESPONSE; valid schema selecting forbidden/unsupported claim
combinations is OUTPUT_REJECTED. Persist no reply on rejection. Never display
raw provider output or unknown claim text as a fallback.

For unsupported topic, claim_ids must be empty and backend renders the fixed
scope explanation: the assistant can summarize recorded accounts, transactions,
budgets and goals but cannot execute financial actions, provide unrestricted
advice, or answer unrelated questions. Supported topics without sufficient facts
use backend missing-data claims. A user asking to mutate a record receives an
explanation to use the normal authenticated screen/API; no financial operation
is invoked. Affordability_context can present available-to-spend and coverage
limitations; it cannot claim a purchase is safe or perform provider-generated
purchase arithmetic/projections.

Entity labels and user text are data, never prompt instructions. Prefer opaque
IDs with bounded labels; exclude transaction descriptions, goal descriptions,
email, credentials, notes and unnecessary profile fields from provider context.
When backend-rendered labels are displayed, use normal escaped text, no raw
HTML. Even injected labels cannot create a monetary claim because only typed
backend templates render values. No model-authored free-text field is accepted.

### 8.2 Minimal provider protocol and identity

```text
ProviderIdentity = {kind: "ollama"|"llama_cpp"|"hosted"|"fake", model: string}
select_claims(request: ImmutableSelectionRequest,
              deadline_monotonic: float) -> BoundedSelectionBytes
```

Request contains only versioned instructions, bounded history/input and the
claim catalog/context projection. The adapter has no DB/session, tenant-query,
tool-execution or mutation handle. Orchestrator validates bytes and owns domain
meaning. Configuration is server-controlled; users/model output cannot choose
provider endpoints, model names, files, tools or settings.

Normalized adapter failures: Timeout, Unavailable, RateLimited, InvalidResponse,
ConfigurationError. Map to the matching persisted provider code after accepted
reservation, except configuration validation normally occurs before reservation
as HTTP 503. Preserve only sanitized error class/retryability, never upstream
body/credentials. No automatic transport retry or fallback model/provider.

| Kind/mode | Contract and trade-offs |
| --- | --- |
| Disabled (default configuration mode) | No outbound calls; new generation/retry receives 503 PROVIDER_DISABLED; existing conversations/history/replays remain readable. No disabled turn is reserved. |
| Local Ollama | First candidate after an actual-machine benchmark; uses an already-installed server and explicitly selected already-present model. No install, pull or model download. Local privacy/control with hardware/RAM/latency/quality constraints and local electricity/storage cost; no claim of unlimited free capacity. |
| Local llama.cpp server | Replaceable later adapter; similar local data control, more deployment/model-format tuning and manual server management. Must pass the same benchmark and grounding schema. |
| Hosted | Future approval only, explicit privacy/cost/account/key review; never automatic cloud fallback. Free tiers can change and have quotas, not unlimited or permanent free operation. |
| Test-only fake | Deterministic test injection with kind exactly fake and a test model ID. Not accepted by production settings/env selectors or production startup. A non-test composition must reject a fake identity; no fake financial answer fallback. |

Use existing httpx with explicit connect/pool/read/write/overall deadlines,
bounded streamed body reads and redirects disabled. Non-streaming application
responses do not prohibit bounded HTTP transport reads. Local defaults must
bind to an explicit loopback host/port allowlist; no user-supplied URL. Disable
environment-derived HTTP proxies for local calls (`trust_env=False`). Validate
scheme, host, port and resolved peer; block redirects, URL credentials,
metadata/link-local and arbitrary network destinations, and fail closed on DNS
changes outside the approved target. Remote/LAN endpoints require explicit
operator-approved configuration and SSRF controls, never a broad private-network
allowlist. Hosted HTTPS targets require a separate approved exact allowlist.

Configuration contract: mode disabled by default; optional approved provider
kind, endpoint, model ID, context/output caps and time/concurrency limits. Limits
may be reduced operationally; raising contract maxima or enabling hosted/fake
production behavior requires a new decision. Missing or invalid configuration
does not auto-discover a model or API key. Never expose provider credentials to
the browser or log settings wholesale.

## 9. Deadlines, cancellation and operations

### 9.1 Independent time bounds

- Overall work deadline: monotonic start + 60 seconds, starting when the
  assistant handler begins bounded request processing, before auth/reservation
  and context construction. It includes reservation, context, dispatch fence,
  inference, validation/rendering, final transaction and cleanup. Server/network
  time before the handler is governed separately by deployment request limits.
- Provider inference deadline: min(dispatch monotonic time + 45 seconds,
  absolute overall monotonic deadline). Pass that absolute deadline into the adapter;
  read timeout alone is insufficient because a slowly arriving body can keep
  resetting read timeouts. No provider phase can extend the 60-second work cap.
- Lease: attempt reservation's PostgreSQL `clock_timestamp()` + 90 seconds.
  This is durable recovery/fencing time, independent of monotonic deadlines.
  No heartbeat or automatic extension in the MVP. Retry starts a new lease.

Before every phase compute remaining total budget. Financial context transaction
has a maximum five seconds, database lock wait maximum two seconds and provider
connect maximum two seconds, each additionally capped by remaining work time.
Pool acquisition, statement, connection, commit and rollback paths also need
bounded remaining-budget handling; existing database defaults alone are not
sufficient. Do not start a phase that cannot finish within the remaining budget.
Reserve time for finalization/cleanup in orchestration rather than granting an
extra 60 seconds to cleanup. The exact phase budget split is a decision before
9E; it cannot raise any of the three independent maxima.

Implementation must use a cancellable end-to-end timeout plus remaining-budget
DB/transport limits, not only cancel an asyncio wrapper around a still-running
blocking thread. Prove bounded context and cleanup behavior in tests. At the
deadline, cancel I/O and stop starting DB work; no detached unbounded cleanup
task. If a safely bounded failure finalization fits, persist the appropriate
failure. Otherwise leave pending; respond 503 WORK_DEADLINE_EXCEEDED when a
response remains possible, or let the disconnected client recover by lookup.
Do not claim timeout means a reservation/commit did not occur.

Cancellation is best-effort at transport/model level. On disconnect cancel work
and clean up within the same total deadline; never claim that a local server
stopped executing. Release local capacity only after the application transport
task is closed; model-side capacity can remain occupied and must be assessed
during benchmarking. Process death cannot run cleanup: pending lease expires,
GET derives interruption, and explicit retry may claim attempt+1. An old model
may still run concurrently with a retry, but stale results cannot persist;
exactly-once physical inference across crashes is not promised. At most one
dispatch per successfully claimed attempt is the application guarantee.

### 9.2 Concurrency, rate limits and logs

MVP: one application worker and one replica; provider execution capacity two
globally and one per user, no queue. Durable constraints/CAS remain correct
under multiple DB clients, but process-local rate/capacity controls are not
global across workers. Do not enable multiple workers/replicas until shared
admission accounting is explicitly designed; no Redis/queue dependency is
implicitly authorized by this specification.

Capacity is acquired only through the atomic all-or-nothing global/per-user
try-acquire in §5.5, never an unprotected check followed by acquisition. The
single cleanup owner releases each acquired token exactly once on every exit;
there is no capacity waiting list or token retained for a replay.

Limits: eight new generation starts per user per rolling 60 seconds; 120
assistant reads per user per 60 seconds; 30 conversation-create/delete/abandon
writes per user per 60 seconds. Retry counts as a generation start only when
claimed and entering provider invocation. Provisional quota reservations count
toward admission and are refunded if invocation never starts, as defined in
§5.5; dispatched failures retain their event. Idempotent generation replay
consumes no generation quota (read/abuse
limits still apply). Bounded process-local limiter storage: maximum 4,096 user
buckets, evict expired buckets; fail closed on new admissions if exhausted.
Unresolved-state resolution must occur before capacity errors, including when
another request is occupying that user's only slot. Supply safe Retry-After on
rate/capacity rejection; no automatic retry loop.

Logs may contain sanitized event name, random request correlation ID, status,
duration, provider kind, attempt number and fixed error code. Do not log prompts,
model output, rendered replies, claim arguments, balances, email, cookie/token,
CSRF, Idempotency-Key, fingerprints or raw request/response bodies. Redact the
Idempotency-Key header in application, reverse-proxy and infrastructure tracing
and disable header/body capture for assistant routes. Since no key is in the
URL, access-log path capture does not expose it; do not retain a legacy URL key
lookup alias. Do not use user/key/financial content as metric labels. No cached
financial context shared across users; no cross-request result cache in MVP.

## 10. Frontend integration contract

Replace MockAssistantService behind a typed authenticated API module and runtime
response validators; never silently fall back to mock replies. Conversation
list/selection, ascending paginated message history, create/delete, turn submit,
lookup, retry, abandon and status handling are explicit operations. Use the
shared credentialed API client and CSRF refresh behavior; do not bypass schemas
or invent optimistic assistant messages.

Show pending, failed, interrupted (derived), completed and abandoned distinctly.
One unresolved turn disables a new message for that conversation; show explicit
retry if can_retry, abandon if can_abandon and conversation deletion. Failed
nonretryable/exhausted turns require abandonment or deletion. Abandoned turns
remain visible as user messages with terminal metadata, not provider failures.
Successful history remains readable while provider is disabled.

On submit generate one key and retain exact normalized payload in memory until
resolved. Store only `{version:1,userId,conversationId,key}` in user-scoped tab
sessionStorage for ambiguous recovery; no message or financial payload. After
network ambiguity/reload first GET `/turns/by-key` with Idempotency-Key. A 404
does not prove an in-flight original cannot subsequently commit; if original
payload is still in memory, only the same key/payload may be resubmitted. After
reload without payload, do not reconstruct or automatically submit different
content. Resolve via lookup/conversation history and require explicit user
action. Do not erase ambiguous markers as though an operation certainly failed.
Tab closure loses this marker; persistent conversation history still exists but
cross-tab operation recovery is not guaranteed by browser metadata.

Poll a live pending turn every two seconds only while its view is active; honor
Retry-After and stop on terminal or derived-interrupted state, navigation,
logout or session change. Polling never invokes the provider. Explicit retry
sends the observed expected_attempt_no and handles replay/CAS conflicts by
rendering current state. Prevent double-clicks locally; backend remains the
authority. DELETE requires confirmation and removes local conversation state
only after confirmation/reconciliation; never turn deletion into financial writes.

On logout/session generation change abort requests, clear rendered user/context
state and ignore late responses even after same-user relogin. Only recover
markers matching the newly authenticated user's ID; never show another user's
marker/history. 401 follows the existing session-expiry flow; CSRF failures
remain distinct. Loading, empty, error, disabled-provider and missing-financial-
data states must be independently renderable. Initial delivery is non-streaming.

## 11. Required verification (future work; none run for this document)

Use existing test infrastructure. PostgreSQL integration tests must use the
repository's isolated safe test-database/schema safeguards, never development
data. SQLite/mocks cannot prove PostgreSQL uniqueness, lock or snapshot behavior.

### 11.1 Contract and unit tests

- Strict UUIDv4 header/body parsing, duplicate/case-varied headers, unknown
  fields, bool-as-int rejection, normalization/fingerprint golden cases,
  pagination, sanitized ErrorDto, no-store on every response including errors.
- Assert §5.3's exact golden UTF-8 bytes, 106-byte length and literal SHA-256;
  compare alternative JSON input key ordering/escaping with the same canonical
  result. Assert surrogate/control escape rules and no Unicode normalization.
- Body boundaries: 4,000 literal four-byte scalars, 4,000 escaped surrogate
  pairs (48,014-byte compact message body), escaped quotes/backslashes and
  permitted controls; 4,001 normalized scalars fail validation. Exactly 65,536
  wire bytes with legal padding is within the wire bound; 65,537 is 413 before
  parsing, including streamed bodies without Content-Length. Reject malformed
  UTF-8, lone surrogates and unsupported Content-Encoding; do not confuse wire
  capacity with model-context admission.
- Atomic capacity and quota: simultaneous global/per-user contenders cannot
  oversubscribe; immediate try-acquire refusal never queues. After each replay,
  reservation race loss, refusal, pre-dispatch failure, provider success/failure,
  cancellation and cleanup, assert zero leaked tokens, no double release, and
  correct provisional refund versus retained dispatched-start quota. Check
  newly claimed retry returns 200 for completed AND failed; live pending replay
  returns 202 with Retry-After.
- Every state/derived condition projection, all persisted failure codes,
  max-attempt boundary, abandoned error clearing and permanent retry prohibition.
- Exact provider schema including duplicate JSON keys, extra fields, unknown
  IDs, inconsistent topic/baseline, unsupported empty selection, injection in
  labels/history, oversized/slow responses, backend-only money rendering.
- Disabled config/no outbound call, production rejection of fake, fake identity
  persistence in tests, no proxy/redirect/cloud/model-download fallback.
- Financial boundary cases: India midnight/month/year/leap transitions,
  opening-date inclusion, archived accounts/categories, deleted transactions,
  uncategorized budgets, full-month budget versus cash-flow-to-date, large exact
  aggregates, negative valid remaining values, overfunded goals, no double
  allocation subtraction, no goal contribution counted as spending.
- Historical full-population comparisons versus paginated/top-N traps, zero
  prior, month-day clamp/unequal lengths, missing/incomplete context notices.
- Monotonic 45/60 deadlines and independent wall-clock 90 lease; context, pool,
  lock, provider slow body, finalization and cancellation all bounded; insufficient
  cleanup budget leaves recoverable pending rather than escaping the deadline.

### 11.2 Required PostgreSQL concurrency and lifecycle tests

Use independent connections and, where relevant, different valid sessions for
the same user; synchronize with barriers/events, not timing guesses. Test the
named uniqueness-recovery branch, not just an early lookup that avoids it.
Controlled test admission/fake capacity may permit reservation contenders;
production rate limits must not hide database race coverage.

1. Same user's same key concurrently submitted to different conversations:
   force both past initial key lookup. Assert 23505 on
   uq_assistant_turns_user_key, rollback of loser user message/turn, one accepted
   operation, conflict for differing conversation fingerprints, and at most
   one provider invocation. Also test same-conversation matching replay and
   same-key/different-content conflict, including different user keys isolated.
2. Simultaneous same conversation UUID creation: matching normalized titles
   yield 201/200 and one row; conflicting titles yield 201/409; foreign-owner
   collision yields non-disclosing 404. Cover a foreign winner in the race and
   an already-existing foreign UUID. Assert primary-key rollback recovery;
   unrelated integrity errors are not replays. Verify per-user creation limit.
3. Distinct keys racing in one conversation: partial unique unresolved
   constraint admits one; loser gets the current owned turn, not capacity busy
   or duplicate dispatch. Test unresolved failed and expired-pending ahead of
   disabled/provider-capacity/rate errors.
4. Concurrent retry with equal expected attempt: exactly one increment, one
   new execution, one user message, at most one reply. Stale expected attempt
   replays current state; attempt 3 cannot retry. Provider/rate refusal consumes
   no attempt. Derived interruption clears on new lease; GET never persists it.
5. Abandon races with retry/completion: live pending cannot abandon, newer
   attempt cannot be abandoned by stale request, exact repeated abandon is
   stable, failed-code clearing is consistent, and new turn can follow abandoned.
6. Provider result arrives after lease expiry or retry: no stale completion or
   error overwrites newer state; no duplicate reply; no attempt count regression.
7. Delete during inference: delete-first discards late result and cascades all
   assistant rows; complete-first result is subsequently removed. No resurrection
   and no financial record change. Ambiguous deletion is recoverable by lookup.
8. Session fencing against real logout/revoke updates: revocation committed
   before the dispatch fence must prevent dispatch. Separately pause after the
   dispatch fence commits but before adapter invocation, commit revocation,
   then resume: dispatch may still occur in this gap (§6); do not assert it is
   prevented. In both the gap case and revocation during inference, logout
   committed before the completion fence prevents successful result persistence
   and publication. Completion-fence-first commit may persist before logout.
   Demonstrate no auth/conversation/turn lock held while fake inference is
   paused. Different-session retry is authorized only for same owner. Verify
   SESSION_INVALIDATED cleanup touches only the already-reserved captured
   pending attempt, cannot overwrite newer/abandoned/deleted operations, and
   cannot be invoked with arbitrary unauthenticated client IDs. Exercise
   session -> optional User -> conversation -> turn order across concurrent
   creation, reservation, deletion and logout, without lock-order inversion.
9. Worker/request interruption after reservation: pending survives, before-lease
   retry is not executed, after expiry response-only interruption appears,
   explicit retry works, max attempts enforced, abandon frees unresolved slot.
10. Commit/network ambiguity: lookup yields committed operation; same-key
    replay cannot create a duplicate. Winner deleted during unique recovery
    returns 404 without dispatch. Database/finalization failures never imply
    uncommitted success or trigger automatic financial/mutation retry.
11. Composite ownership FKs, state checks, sequence gaps and reply linkage,
    legacy messages, migration upgrade/downgrade, deletion cascades, and repeatable
    financial snapshot while concurrent domain writes commit. Establish the
    snapshot using §7.1's first statement, verify observed_at is database-sampled
    rather than pre-query application time, then commit a domain write from
    another connection and show all later reporting reads exclude it. Cover
    the clock-sample/snapshot visibility distinction and Asia/Kolkata midnight
    date propagation without pretending observed_at is a commit cutoff. Verify authoritative
    reporting equivalence and no assistant financial writes.

### 11.3 Frontend and release verification

Exercise real API-client invocation through provider/page paths: authenticated
list/select, history pages, create replay, pending submission, ambiguous lookup,
failed/interrupted/exhausted/abandoned rendering, explicit retry/abandon, deletion
confirmation, disabled provider, CSRF, 401, runtime parsing, session-switch and
late-response isolation. Ensure polling stops appropriately and no financial
mutation API is called. Run full frontend tests, typecheck/build/lint and backend
unit/PostgreSQL suites only in the authorized implementation phases. A live
browser session and actual-machine provider benchmark are release gates, not
substitutes for deterministic tests.

## 12. Implementation sequence and decision gates

Each task is independently reviewable; paths below are proposed targets, not
authorization to modify them in Phase 9B. A migration is required only in 9C.2.

| Step | Scope / likely files | Dependencies and tests | Acceptance / migration |
| --- | --- | --- | --- |
| 9C.1 | Contract schemas/enums and golden tests; proposed backend/app/schemas/assistant.py and tests/test_assistant_contracts.py | Approval of this specification; strict API, fingerprints, states, fake boundary and grounding schema tests | Frozen cross-layer DTO/error contracts, no provider calls; no migration. |
| 9C.2 | AssistantTurn model, registration, one forward Alembic revision; models/assistant_turn.py, models/__init__.py, alembic/versions | 9C.1; verify actual head read-only before generating revision; isolated PostgreSQL constraints/cascade/upgrade tests | All ownership/state/unique constraints implemented, legacy messages preserved; migration required, separate application approval. |
| 9C.3 | Conversation routes/service, owner-scoped history and replay-safe create/delete; api/assistant_routes.py, services/assistant_conversations.py | 9C.2; UUID creation race, ownership, limits, pagination/delete tests | Contract-complete conversation API with no financial writes; no additional migration. |
| 9C.4 | Turn lifecycle/reservation/recovery/retry/abandon/fencing; services/assistant_turns.py and route extensions | 9C.2–9C.3; deterministic fake injection; all idempotency, lease, session/delete races | One unresolved turn, correct constraint recovery and attempt CAS; fake never production-configurable; no additional migration. |
| 9D | Shared reporting and bounded context; services/financial_reporting.py, services/assistant_context.py; narrow authoritative reader refactors | 9C.1 and financial semantics fixtures; full historical/snapshot equivalence tests | Complete date-correct authoritative aggregates and notices, no duplicated financial definitions; no migration. |
| 9E | Claim catalog, validator/renderer and orchestration; services/assistant_grounding.py, services/assistant_orchestrator.py | 9C.4 + 9D; timeout/cancellation/fencing/security tests using fake | Only backend-authored supported claims reach users; 45/60/90 bounds enforced; no migration. |
| 9F | httpx local adapter, explicit configuration, actual-machine benchmark documentation/results in a separately approved task | 9E; SSRF/transport/schema tests, manual benchmark and operational approval | Remains disabled until selected model passes local quality/resource/deadline gates; no installs/downloads by implication, no migration. |
| 9G | Typed assistant API/validators/provider, conversation UI and recovery; frontend services/api, types/assistant.ts, hooks/useAssistantConversation.ts, pages/AssistantPage.tsx | 9C APIs + 9E contracts; mocked transport and full page/session regression tests | Persistent non-streaming lifecycle UI, no mock fallback, no cross-session leakage; no migration. |
| 9H | Integrated verification and release readiness | All earlier steps; safe PostgreSQL suite, full frontend checks, live browser, local benchmark, logs/limits/deployment review | Explicit release approval; no automatic provider enablement or cloud fallback. |

Decisions still required, without weakening the frozen contract:

- Before 9E: choose the concrete async/synchronous DB cancellation and bounded
  pool/commit strategy and phase/cleanup budget split. Demonstrate that context
  and cleanup do not escape 60 seconds; a wrapper timeout alone is insufficient.
- Before 9F: benchmark the actual machine, already-present candidate models,
  reliable token accounting, JSON-selection reliability, memory/CPU/GPU use,
  cold/warm latency, cancellation behavior and concurrency. No model is selected
  by this specification. If none passes 45/60-second limits and grounding tests,
  remain disabled and seek a new decision; do not silently raise limits.
- Before 9F: approve the exact local endpoint/peer allowlist and deployment
  topology; no assumption that Ollama is installed or reachable from backend.
- Before multi-worker deployment: design shared rate/capacity enforcement and
  re-evaluate model-side concurrency after cancellation. MVP stays single worker.
- Any hosted provider, new paid service/dependency, automatic download,
  unrestricted prose/tools, conversation renaming, tombstone retention or
  additional financial facts requires a separate reviewed contract change.

These are bounded implementation/operational gates, not permission to leave
ownership, state, idempotency, error or grounding semantics undefined.

## 13. Consistency and approval boundary

The same four persisted states, three-attempt limit, user-wide key scope and
90-second lease govern persistence, HTTP, orchestration and frontend. Interrupted
is a response-only projection of expired pending; abandoned is terminal with no
failure code and no unresolved slot. Provider dispatch occurs only after a
committed reservation and dispatch fence; completion is separately session- and
attempt-fenced. Financial facts remain authoritative and read-only; only
validated backend templates become user-visible financial claims.

This document is internally consistent across those contracts subject to the
explicit implementation gates above. No tests, database commands, migration,
dependency installation or implementation were performed in creating it. Stop
at Phase 9B; Phase 9C.1 requires explicit review and approval.
