"""C4 durable turn lifecycle. No financial context or production executor.

Only an explicit FastAPI test dependency override can supply the test executor.
The executor receives immutable operation identity, never a DB/session or tools,
and returns an enum outcome, never prose or financial claims. Real orchestration
and grounded rendering remain separate, later phases.
"""

from dataclasses import dataclass
from datetime import timedelta
import asyncio
import logging
import time
import threading
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import anyio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import AssistantMessage, AssistantTurn
from app.schemas.assistant import (
    LEASE_SECONDS, MAX_TURNS_PER_CONVERSATION, PROVIDER_DEADLINE_SECONDS,
    TURN_ERROR_MESSAGES, HttpErrorCode, PersistedFailureCode, ProviderIdentity,
    ProviderKind, TurnDto, TurnError, TurnStatus,
)
from app.services import assistant_conversations as conversations
from app.services.assistant_contracts import (
    AttemptAction, ContractViolation, IdempotencyResult, abandon_contract,
    compare_fingerprints, project_lifecycle, replay_http_status, retry_contract,
    submission_fingerprint,
)
from app.services.authentication import get_current_user

from app.services.assistant_orchestrator import GroundedAnswer, GroundedExecution
from app.services.assistant_contracts import GroundingContractViolation

logger = logging.getLogger(__name__)


def get_test_executor():
    """Production composition is always disabled; no settings/env fake selector."""
    return None


@dataclass(frozen=True)
class ExecutionAttempt:
    user_id: UUID
    conversation_id: UUID
    turn_id: UUID
    attempt_no: int


class _ExecutionGate:
    """Test coordination across loops/threads, with no blocking executor thread.

    Synchronous wait is for test observers only. Executor waits always use
    wait_until with an absolute deadline; cancellation removes the waiter.
    """
    __slots__ = ("_event", "_lock", "_waiters")

    def __init__(self, *, opened=False):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._waiters = set()
        if opened:
            self._event.set()

    def set(self):
        with self._lock:
            self._event.set()
            for loop, future in tuple(self._waiters):
                def wake(future=future):
                    if not future.done():
                        future.set_result(None)
                loop.call_soon_threadsafe(wake)

    def is_set(self):
        return self._event.is_set()

    def clear(self):
        with self._lock:
            self._event.clear()

    def wait(self, timeout=None):
        return self._event.wait(timeout)

    async def wait_until(self, deadline):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        waiter = (loop, future)
        with self._lock:
            if self._event.is_set():
                future.set_result(None)
            else:
                self._waiters.add(waiter)
        try:
            with anyio.fail_after(max(0, deadline - time.monotonic())):
                await future
        finally:
            with self._lock:
                self._waiters.discard(waiter)


class _ExecutorDeadline(Exception):
    """Execution has terminated but no budget remains for finalization."""


class TestExecutor:
    """Sealed deterministic C4 test boundary, never a production adapter.

    No caller-supplied coroutine/transport/cleanup callback is accepted: such a
    callback could ignore cancellation, which an outer timeout cannot fix.
    All owned waits and shutdown are bounded here. Real provider adapters remain
    later-phase work and cannot be substituted through this test boundary.
    """
    __test__ = False
    __slots__ = ("outcome", "paused", "calls", "entered", "release", "cancelled", "terminated", "shutdown",
                 "preparation_entered", "preparation_terminated", "preparation_release")
    identity = ProviderIdentity(kind="fake", model="c4-test-only")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("C4 TestExecutor cannot be subclassed")

    def __init__(self, outcome=None, *, paused=False, shutdown_blocked=False, preparation_paused=False):
        self.outcome, self.paused = outcome, paused
        self.calls = []
        self.entered, self.release = _ExecutionGate(), _ExecutionGate()
        self.cancelled, self.terminated = _ExecutionGate(), _ExecutionGate()
        self.shutdown = _ExecutionGate(opened=not shutdown_blocked)
        self.preparation_entered = _ExecutionGate()
        self.preparation_terminated = _ExecutionGate(opened=True)
        self.preparation_release = _ExecutionGate(opened=not preparation_paused)

    async def prepare(self, *, deadline):
        """Resource-free TEST seam, not serialization/counting/process support.

        Sole owned work is a cancellation-safe loop future. No callbacks,
        threads or child processes are admitted by this seam.
        """
        self.preparation_terminated.clear()
        self.preparation_entered.set()
        try:
            await self.preparation_release.wait_until(deadline)
        finally:
            self.preparation_terminated.set()

    async def execute(self, attempt: ExecutionAttempt, *, deadline_monotonic: float,
                      work_deadline_monotonic: float) -> PersistedFailureCode | None:
        """Inference uses its cap; cancellation/shutdown share the work deadline."""
        self.entered.clear()
        self.cancelled.clear()
        self.terminated.clear()
        self.calls.append(attempt)
        self.entered.set()
        try:
            if self.paused:
                await self.release.wait_until(deadline_monotonic)
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome
        except anyio.get_cancelled_exc_class():
            self.cancelled.set()
            raise
        finally:
            shutdown_expired = False
            try:
                # Shield parent cancellation, never our own absolute deadline.
                with anyio.CancelScope(shield=True, deadline=work_deadline_monotonic) as scope:
                    try:
                        await self.shutdown.wait_until(work_deadline_monotonic)
                    except TimeoutError:
                        shutdown_expired = True
                shutdown_expired = shutdown_expired or scope.cancelled_caught
            finally:
                # No thread, transport task or gate waiter survives this point.
                self.terminated.set()
            if shutdown_expired or time.monotonic() >= work_deadline_monotonic:
                raise _ExecutorDeadline()


class TurnConflict(ContractViolation):
    def __init__(self, code, current_turn=None):
        super().__init__(code)
        self.current_turn = current_turn


def now(db):
    return conversations._utc(db.scalar(select(func.clock_timestamp())))


def by_key(db, user_id, key):
    return db.scalar(select(AssistantTurn).where(
        AssistantTurn.user_id == user_id, AssistantTurn.idempotency_key == key,
    ).execution_options(populate_existing=True))


def owned_turn(db, user_id, conversation_id, turn_id, *, lock=False):
    statement = select(AssistantTurn).where(
        AssistantTurn.user_id == user_id, AssistantTurn.conversation_id == conversation_id,
        AssistantTurn.id == turn_id,
    )
    if lock:
        statement = statement.with_for_update()
    turn = db.scalar(statement.execution_options(populate_existing=True))
    if turn is None:
        raise ContractViolation(HttpErrorCode.TURN_NOT_FOUND)
    return turn


def unresolved(db, user_id, conversation_id):
    return db.scalar(select(AssistantTurn).where(
        AssistantTurn.user_id == user_id, AssistantTurn.conversation_id == conversation_id,
        AssistantTurn.status.in_(("pending", "failed")),
    ).execution_options(populate_existing=True))


def turn_dto(db, turn):
    observed = now(db)
    projection = project_lifecycle(
        status=TurnStatus(turn.status), attempt_no=turn.attempt_no,
        lease_expires_at=conversations._utc(turn.lease_expires_at),
        error_code=PersistedFailureCode(turn.error_code) if turn.error_code else None,
        observed_at=observed,
    )
    positions = [turn.user_sequence_no]
    if turn.assistant_sequence_no is not None:
        positions.append(turn.assistant_sequence_no)
    messages = {message.sequence_no: conversations._message_dto(message, conversations._metadata(turn))
                for message in db.scalars(select(AssistantMessage).where(
                    AssistantMessage.user_id == turn.user_id,
                    AssistantMessage.conversation_id == turn.conversation_id,
                    AssistantMessage.sequence_no.in_(positions),
                ))}
    return TurnDto(
        id=turn.id, conversation_id=turn.conversation_id, idempotency_key=turn.idempotency_key,
        status=turn.status, attempt_no=turn.attempt_no,
        user_message=messages[turn.user_sequence_no],
        assistant_message=messages.get(turn.assistant_sequence_no),
        **{field: conversations._utc(getattr(turn, field)) for field in (
            "created_at", "attempt_started_at", "attempt_finished_at", "lease_expires_at", "context_as_of")},
        financial_date=turn.financial_date,
        lease_expired=projection.lease_expired, can_retry=projection.can_retry,
        can_abandon=projection.can_abandon,
        error=TurnError(code=projection.error_code, message=TURN_ERROR_MESSAGES[projection.error_code])
        if projection.error_code else None,
    )


def lookup(db, user_id, key):
    turn = by_key(db, user_id, key)
    if turn is None:
        raise ContractViolation(HttpErrorCode.TURN_NOT_FOUND)
    return turn_dto(db, turn)


def get_turn(db, user_id, conversation_id, turn_id):
    conversations.owned_conversation(db, user_id=user_id, conversation_id=conversation_id)
    return turn_dto(db, owned_turn(db, user_id, conversation_id, turn_id))


def reauthenticate(db, authenticated):
    current = get_current_user(db, session_token=authenticated.session_token)
    original = authenticated.current_user
    if current is None or (current.user_id, current.session_id) != (original.user_id, original.session_id):
        raise ContractViolation(HttpErrorCode.AUTHENTICATION_REQUIRED)


def _replay(db, turn, fingerprint):
    if compare_fingerprints(bytes(turn.request_fingerprint), fingerprint) == IdempotencyResult.CONFLICT:
        raise ContractViolation(HttpErrorCode.IDEMPOTENCY_CONFLICT)
    return turn_dto(db, turn)


def _admission_state(db, authenticated, conversation_id, *, key=None, fingerprint=None,
                     turn_id=None, expected=None):
    """Session is locked by caller; conversation before turn, on every recheck."""
    user_id = authenticated.current_user.user_id
    conversations.owned_conversation(db, user_id=user_id, conversation_id=conversation_id, lock=True)
    if turn_id is not None:
        turn = owned_turn(db, user_id, conversation_id, turn_id, lock=True)
        dto = turn_dto(db, turn)
        try:
            action = retry_contract(dto, expected)
        except ContractViolation as error:
            raise TurnConflict(error.code, dto) from None
        return (dto if action == AttemptAction.REPLAY else None), turn
    existing = by_key(db, user_id, key)
    if existing is not None:
        return _replay(db, existing, fingerprint), existing
    blocking = unresolved(db, user_id, conversation_id)
    if blocking is not None:
        raise TurnConflict(HttpErrorCode.UNRESOLVED_TURN, turn_dto(db, blocking))
    return None, None


def _new_turn(db, authenticated, conversation_id, key, fingerprint, content, identity):
    user_id = authenticated.current_user.user_id
    count = db.scalar(select(func.count()).select_from(AssistantTurn).where(
        AssistantTurn.user_id == user_id, AssistantTurn.conversation_id == conversation_id,
    ))
    last_message = db.scalar(select(func.max(AssistantMessage.sequence_no)).where(
        AssistantMessage.user_id == user_id, AssistantMessage.conversation_id == conversation_id,
    )) or 0
    last_reserved = db.scalar(select(func.max(AssistantTurn.user_sequence_no + 1)).where(
        AssistantTurn.user_id == user_id, AssistantTurn.conversation_id == conversation_id,
    )) or 0
    sequence = max(last_message, last_reserved) + 1
    if count >= MAX_TURNS_PER_CONVERSATION or sequence > 2**31 - 2:
        raise ContractViolation(HttpErrorCode.TURN_LIMIT_REACHED)
    started = now(db)
    db.add(AssistantMessage(user_id=user_id, conversation_id=conversation_id,
                            sequence_no=sequence, role="user", content=content, created_at=started))
    db.flush()
    turn = AssistantTurn(
        id=uuid4(), user_id=user_id, conversation_id=conversation_id, idempotency_key=key,
        request_fingerprint=fingerprint, user_sequence_no=sequence, assistant_sequence_no=None,
        status="pending", attempt_no=1, created_at=started, attempt_started_at=started,
        lease_expires_at=started + timedelta(seconds=LEASE_SECONDS),
        provider_kind=identity.kind.value, model_name=identity.model, contract_version=1,
    )
    db.add(turn)
    db.flush()
    return turn


def _retry_turn(db, turn, identity):
    turn.attempt_no += 1
    turn.status = "pending"
    turn.attempt_started_at = now(db)
    turn.lease_expires_at = turn.attempt_started_at + timedelta(seconds=LEASE_SECONDS)
    turn.attempt_finished_at = turn.error_code = None
    turn.context_as_of = turn.financial_date = None
    turn.provider_kind, turn.model_name = identity.kind.value, identity.model
    db.flush()
    return turn


def _constraint(error):
    original = error.orig
    if (getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)) != "23505":
        return None
    return getattr(getattr(original, "diag", None), "constraint_name", None)


def _recover(db, authenticated, conversation_id, key, fingerprint, constraint):
    # Caller rolled back the entire failed insert, including the user message.
    reauthenticate(db, authenticated)
    user_id = authenticated.current_user.user_id
    existing = by_key(db, user_id, key)
    if existing is not None:
        if compare_fingerprints(bytes(existing.request_fingerprint), fingerprint) == IdempotencyResult.CONFLICT:
            raise ContractViolation(HttpErrorCode.IDEMPOTENCY_CONFLICT)
        # Recovery runs in READ COMMITTED after rollback. Stabilize the winner
        # before projecting its messages, so deletion between lookup and DTO
        # construction is a not-found, never a partial replay or resurrection.
        try:
            conversations.owned_conversation(db, user_id=user_id,
                                             conversation_id=existing.conversation_id, lock=True)
            existing = owned_turn(db, user_id, existing.conversation_id, existing.id, lock=True)
        except ContractViolation:
            raise ContractViolation(HttpErrorCode.TURN_NOT_FOUND) from None
        return _replay(db, existing, fingerprint)
    if constraint == "uq_assistant_turns_user_key":
        raise ContractViolation(HttpErrorCode.TURN_NOT_FOUND)
    conversations.owned_conversation(db, user_id=user_id, conversation_id=conversation_id, lock=True)
    blocking = unresolved(db, user_id, conversation_id)
    raise TurnConflict(HttpErrorCode.UNRESOLVED_TURN if blocking else HttpErrorCode.ATTEMPT_CONFLICT,
                       turn_dto(db, blocking) if blocking else None)


def _fenced_turn(db, authenticated, attempt, *, authenticate=True):
    if authenticate:
        reauthenticate(db, authenticated)
    conversations.owned_conversation(db, user_id=attempt.user_id,
                                     conversation_id=attempt.conversation_id, lock=True)
    turn = owned_turn(db, attempt.user_id, attempt.conversation_id, attempt.turn_id, lock=True)
    if turn.status != "pending" or turn.attempt_no != attempt.attempt_no or now(db) >= turn.lease_expires_at:
        raise TurnConflict(HttpErrorCode.ATTEMPT_CONFLICT, turn_dto(db, turn))
    return turn


def dispatch_fence(db, authenticated, attempt, context=None):
    turn = _fenced_turn(db, authenticated, attempt)
    # Test-only observation, NOT a financial snapshot or context implementation.
    turn.context_as_of = context.context_as_of if context is not None else now(db)
    turn.financial_date = (context.financial_date if context is not None else
                           turn.context_as_of.astimezone(ZoneInfo("Asia/Kolkata")).date())
    db.commit()


def _fail(turn, finished, code):
    turn.status = "failed"
    turn.attempt_finished_at = finished
    turn.lease_expires_at = None
    turn.error_code = code.value


def cleanup_invalid_session(db, attempt):
    """Internal execution-owner capability only. No caller-supplied IDs endpoint.

    The frozen attempt was captured only after authenticated reservation commit.
    Never acquire a session lock after conversation/turn locks in this cleanup.
    """
    try:
        turn = _fenced_turn(db, None, attempt, authenticate=False)
        _fail(turn, now(db), PersistedFailureCode.SESSION_INVALIDATED)
        db.commit()
    except ContractViolation:
        db.rollback()  # Deleted, stale, expired or abandoned: leave untouched.
    except SQLAlchemyError:
        # Best-effort internal cleanup must not turn authentication loss into
        # a successful answer (or leak a storage exception). Lease recovery is
        # still available if this narrowly scoped cleanup could not commit.
        db.rollback()
        logger.warning("assistant_session_cleanup_failed")


def complete(db, authenticated, attempt, outcome):
    turn = _fenced_turn(db, authenticated, attempt)
    finished = now(db)
    if outcome is None or type(outcome) is GroundedAnswer:
        db.add(AssistantMessage(
            user_id=attempt.user_id, conversation_id=attempt.conversation_id,
            sequence_no=turn.user_sequence_no + 1, role="assistant",
            content=outcome.text if type(outcome) is GroundedAnswer else "Test execution completed.", created_at=finished,
        ))
        db.flush()
        turn.assistant_sequence_no = turn.user_sequence_no + 1
        turn.status = "completed"
        turn.attempt_finished_at = finished
        turn.lease_expires_at = None
    else:
        _fail(turn, finished, outcome)
    conversation = conversations.owned_conversation(
        db, user_id=attempt.user_id, conversation_id=attempt.conversation_id)
    conversation.updated_at = finished
    db.flush()
    dto = turn_dto(db, turn)
    db.commit()
    return dto


def abandon(db, authenticated, conversation_id, turn_id, expected):
    user_id = authenticated.current_user.user_id
    conversation = conversations.owned_conversation(db, user_id=user_id, conversation_id=conversation_id, lock=True)
    turn = owned_turn(db, user_id, conversation_id, turn_id, lock=True)
    dto = turn_dto(db, turn)
    try:
        action = abandon_contract(dto, expected)
    except ContractViolation as error:
        raise TurnConflict(error.code, dto) from None
    if action == AttemptAction.CLAIM:
        turn.status, turn.error_code, turn.lease_expires_at = "abandoned", None, None
        turn.attempt_finished_at = now(db)
        conversation.updated_at = turn.attempt_finished_at
        db.flush()
        dto = turn_dto(db, turn)
    db.commit()
    return dto


async def _execute(executor, attempt, deadline, receive, ticket, prepared=None):
    if type(executor) is GroundedExecution and not executor.provider.supports_bounded_shutdown:
        raise ContractViolation(HttpErrorCode.PROVIDER_CONFIGURATION_INVALID)
    disconnected = False
    shutdown_expired = False
    outcome = None
    async with anyio.create_task_group() as group:
        async def monitor():
            nonlocal disconnected
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected = True
                    group.cancel_scope.cancel()
                    return

        if receive is not None:
            group.start_soon(monitor)
        try:
            if receive is not None:
                # Give an already queued disconnect priority over invocation.
                # Quota remains provisional until we actually call execute.
                await anyio.lowlevel.checkpoint()
            with anyio.fail_after(min(PROVIDER_DEADLINE_SECONDS, max(0, deadline - time.monotonic()))):
                if time.monotonic() >= deadline:
                    raise ContractViolation(HttpErrorCode.WORK_DEADLINE_EXCEEDED)
                ticket.start()
                outcome = await executor.execute(prepared if type(executor) is GroundedExecution else attempt, deadline_monotonic=min(
                    deadline, time.monotonic() + PROVIDER_DEADLINE_SECONDS),
                    work_deadline_monotonic=deadline)
            if receive is not None:
                await anyio.lowlevel.checkpoint()
            if outcome is not None and not (type(executor) is GroundedExecution and type(outcome) is GroundedAnswer) and (not isinstance(outcome, PersistedFailureCode)
                                       or outcome == PersistedFailureCode.SESSION_INVALIDATED):
                outcome = PersistedFailureCode.INVALID_PROVIDER_RESPONSE
        except GroundingContractViolation as error:
            outcome = error.code
        except _ExecutorDeadline:
            shutdown_expired = True
        except TimeoutError:
            outcome = PersistedFailureCode.PROVIDER_TIMEOUT
        except Exception:
            outcome = PersistedFailureCode.INTERNAL_FAILURE
        finally:
            group.cancel_scope.cancel()  # Join the receive monitor as well.
    if type(executor) is GroundedExecution and not executor.provider.termination_complete.is_set():
        # Defense in depth: an unsupported transport cannot enter this path via
        # generate. Never publish/release as though transport shutdown finished.
        raise ContractViolation(HttpErrorCode.PROVIDER_CONFIGURATION_INVALID)
    if disconnected or shutdown_expired:
        # The transport is gone. Never finalize a fabricated completion; the
        # committed pending attempt remains recoverable through its lease.
        raise ContractViolation(HttpErrorCode.WORK_DEADLINE_EXCEEDED)
    return outcome


async def _generate(database, authenticated, conversation_id, *, admission, executor, test_environment,
                   deadline, key=None, content=None, turn_id=None, expected=None, receive=None):
    """Each DB phase owns a worker-local Session; only frozen values cross out."""
    fingerprint = submission_fingerprint(conversation_id, content) if turn_id is None else None
    arguments = dict(key=key, fingerprint=fingerprint, turn_id=turn_id, expected=expected)

    def inspect(db):
        reauthenticate(db, authenticated)
        dto, _ = _admission_state(db, authenticated, conversation_id, **arguments)
        db.commit()
        return dto

    dto = await database.run(inspect, deadline=deadline)
    if dto is not None:
        return dto, replay_http_status(dto)
    ticket, retry_after = admission.reserve_quota(authenticated.current_user.user_id)
    try:
        refusal = HttpErrorCode.RATE_LIMITED if ticket is None else None
        if refusal is None:
            if executor is None:
                refusal = HttpErrorCode.PROVIDER_DISABLED
            elif not (
                (test_environment and type(executor) is TestExecutor and executor.identity.kind == ProviderKind.FAKE)
                or (type(executor) is GroundedExecution and executor.deployment_approved is True
                    and executor.supports_execution(test_environment=test_environment) and executor.identity.kind in {ProviderKind.OLLAMA, ProviderKind.LLAMA_CPP})
            ):
                refusal = HttpErrorCode.PROVIDER_CONFIGURATION_INVALID
            elif not ticket.acquire_capacity():
                refusal, retry_after = HttpErrorCode.GENERATION_BUSY, 2
        if refusal is not None and ticket is not None:
            ticket.close()
            ticket = None

        def reserve(db):
            reauthenticate(db, authenticated)
            dto, turn = _admission_state(db, authenticated, conversation_id, **arguments)
            if dto is not None:
                db.commit()
                return dto
            if refusal is not None:
                error = ContractViolation(refusal)
                error.retry_after = retry_after
                raise error
            try:
                turn = (_new_turn(db, authenticated, conversation_id, key, fingerprint, content, executor.identity)
                        if turn_id is None else _retry_turn(db, turn, executor.identity))
                conversation = conversations.owned_conversation(
                    db, user_id=turn.user_id, conversation_id=conversation_id)
                conversation.updated_at = turn.attempt_started_at
                attempt = ExecutionAttempt(turn.user_id, conversation_id, turn.id, turn.attempt_no)
                db.commit()
                return attempt
            except IntegrityError as error:
                db.rollback()
                constraint = _constraint(error)
                if constraint not in {"uq_assistant_turns_user_key", "uq_assistant_turns_unresolved_conversation"} or turn_id is not None:
                    raise ContractViolation(HttpErrorCode.INTERNAL_ERROR) from None
                dto = _recover(db, authenticated, conversation_id, key, fingerprint, constraint)
                db.commit()
                return dto

        reserved = await database.run(reserve, deadline=deadline)
        if isinstance(reserved, TurnDto):
            return reserved, replay_http_status(reserved)
        attempt = reserved
        try:
            prepared = None
            if type(executor) is GroundedExecution:
                try:
                    prepared = await executor.prepare(database, authenticated, attempt, deadline=deadline)
                except GroundingContractViolation as error:
                    dto = await database.run(lambda db: complete(db, authenticated, attempt, error.code), deadline=deadline)
                    return dto, 201 if turn_id is None else 200
                await database.run(lambda db: dispatch_fence(db, authenticated, attempt, prepared[0]), deadline=deadline)
            else:
                # Sealed test seam only; operation-wide disconnect monitoring is
                # active. Production preparation remains refused at admission.
                await executor.prepare(deadline=deadline)
                await database.run(lambda db: dispatch_fence(db, authenticated, attempt), deadline=deadline)
            if time.monotonic() >= deadline:
                raise ContractViolation(HttpErrorCode.WORK_DEADLINE_EXCEEDED)
            outcome = await _execute(executor, attempt, deadline, receive, ticket, prepared)
            dto = await database.run(lambda db: complete(db, authenticated, attempt, outcome), deadline=deadline)
            return dto, 201 if turn_id is None else 200
        except ContractViolation as error:
            if error.code == HttpErrorCode.AUTHENTICATION_REQUIRED and deadline - time.monotonic() > 0.02:
                try:
                    # Optional cleanup gets at most half the remaining budget;
                    # preserve time to report the original 401 and release the
                    # capacity token. There is never an extra cleanup deadline.
                    cleanup_deadline = time.monotonic() + (deadline - time.monotonic()) / 2
                    await database.run(lambda db: cleanup_invalid_session(db, attempt), deadline=cleanup_deadline)
                except (ContractViolation, SQLAlchemyError):
                    logger.warning("assistant_session_cleanup_failed")
            raise
    finally:
        # database.run joins every worker and _execute joins cancellation before
        # this single release owner runs. No Session exists on this event loop.
        if ticket is not None:
            ticket.close()


async def generate(database, authenticated, conversation_id, *, admission, executor, test_environment,
                   deadline, key=None, content=None, turn_id=None, expected=None, receive=None):
    """One receive owner from bounded-body completion through finalization.

    Routes finish parsing the body before calling here. _execute receives None,
    so no competing consumer exists. Cancellation joins the operation and its
    owned phases before their single capacity-release finally completes.
    """
    disconnected = False
    result = None
    failure = None
    async with anyio.create_task_group() as group:
        async def monitor():
            nonlocal disconnected
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected = True
                    group.cancel_scope.cancel()
                    return

        if receive is not None:
            group.start_soon(monitor)
        try:
            await anyio.lowlevel.checkpoint()
            result = await _generate(database, authenticated, conversation_id,
                admission=admission, executor=executor, test_environment=test_environment,
                deadline=deadline, key=key, content=content, turn_id=turn_id,
                expected=expected, receive=None)
            await anyio.lowlevel.checkpoint_if_cancelled()
        except Exception as error:
            failure = error  # Preserve the existing sanitized route mapping.
        finally:
            group.cancel_scope.cancel()
    if disconnected:
        # A committed reservation/result is not represented as rolled back.
        raise ContractViolation(HttpErrorCode.WORK_DEADLINE_EXCEEDED)
    if failure is not None:
        raise failure
    return result
