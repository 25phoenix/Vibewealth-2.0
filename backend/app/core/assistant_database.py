"""Deadline-bound synchronous PostgreSQL phases, entirely owned by workers.

No pooled connection can outlive a phase. psycopg's nonblocking libpq waits
bound connection setup and every protocol exchange (including COMMIT/ROLLBACK).
On deadline we close the connection locally; an in-flight COMMIT is ambiguous,
never reported as success. No cancellation request with its own extra timeout
is sent, and no abandoned database thread is used.
"""

from contextvars import ContextVar
from dataclasses import dataclass
import ipaddress
import time

import anyio
import psycopg
from fastapi import Request
from psycopg import waiting
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.database import engine
from app.schemas.assistant import CONNECT_DEADLINE_SECONDS, LOCK_DEADLINE_SECONDS, HttpErrorCode
from app.services.assistant_contracts import ContractViolation


def expired():
    return ContractViolation(HttpErrorCode.WORK_DEADLINE_EXCEEDED)


@dataclass(frozen=True)
class Budget:
    deadline: float

    def remaining(self):
        value = self.deadline - time.monotonic()
        if value <= 0:
            raise expired()
        return value


_budget = ContextVar("assistant_database_budget")


def _guard(gen):
    """Check the absolute budget on readiness and polling wakeups alike."""
    try:
        _budget.get().remaining()
        state = next(gen)
        while True:
            ready = yield state
            _budget.get().remaining()
            state = gen.send(ready)
    except StopIteration as result:
        return result.value
    finally:
        gen.close()


class DeadlineConnection(psycopg.Connection):
    def wait(self, gen, interval=0.01, timeout=None):
        try:
            remaining = _budget.get().remaining()
            return waiting.wait(_guard(gen), self.pgconn.socket, interval=0.01,
                                timeout=min(remaining, timeout) if timeout is not None else remaining)
        except (ContractViolation, psycopg.errors._WaitTimeout):
            self.close()  # PQfinish: local close, no rollback/network round trip.
            raise expired() from None


class DeadlineSession(Session):
    def commit(self):
        _budget.get().remaining()
        super().commit()
        _budget.get().remaining()  # Lost commit acknowledgement is NOT success.


class AssistantDatabase:
    def __init__(self, source=engine):
        # Preserve the source URL and schema mapping, never its live connection.
        args, params = source.dialect.create_connect_args(source.url)
        if args:
            raise ValueError("Assistant database requires structured connection parameters")
        params = dict(params)
        adapter_context = params.pop("context", None)
        host = params.get("host", "localhost")
        if host == "localhost":
            params["hostaddr"] = "127.0.0.1"
        else:
            # Fail closed instead of allowing blocking DNS/service discovery to
            # escape the connection deadline. Local checkout uses localhost.
            try:
                params["hostaddr"] = str(ipaddress.ip_address(host))
            except ValueError:
                raise ValueError("Assistant database requires localhost or a literal address") from None
        params["options"] = "-c statement_timeout=2000 -c lock_timeout=2000"

        def connect():
            budget = _budget.get()
            limit = min(CONNECT_DEADLINE_SECONDS, budget.remaining())
            # Unlike connect_timeout's integer rounding, wait_conn accepts the
            # exact remaining subsecond budget. hostaddr avoids synchronous DNS.
            try:
                conninfo = make_conninfo(**params)
            except Exception:
                raise ContractViolation(HttpErrorCode.DATABASE_UNAVAILABLE) from None
            def connection_generator():
                pgconn = yield from psycopg.generators.connect(conninfo)
                connection = DeadlineConnection(pgconn)
                if adapter_context is not None:
                    # Same adapter initialization as psycopg.Connection.connect;
                    # context is a driver option, never a libpq conninfo field.
                    connection._adapters = psycopg.adapt.AdaptersMap(adapter_context.adapters)
                return connection
            gen = connection_generator()
            try:
                return waiting.wait_conn(_guard(gen), interval=0.01, timeout=limit)
            except psycopg.errors._WaitTimeout:
                gen.close()
                raise expired() from None
            except psycopg.Error:
                raise ContractViolation(HttpErrorCode.DATABASE_UNAVAILABLE) from None

        def limits(connection, cursor, statement, parameters, context, executemany):
            remaining_ms = max(1, int(_budget.get().remaining() * 1000))
            # SET LOCAL does not acquire an MVCC snapshot. SELECT set_config
            # would establish one before the reporting observation statement.
            for setting, value in (
                ('statement_timeout', remaining_ms),
                ('lock_timeout', min(LOCK_DEADLINE_SECONDS * 1000, remaining_ms)),
                ('idle_in_transaction_session_timeout', remaining_ms),
            ):
                cursor.execute(f"SET LOCAL {setting} = '{value}ms'")


        def make_engine():
            # A phase-local pool also avoids SQLAlchemy's shared first-connect
            # initialization mutex: another request's initialization may not
            # hold this request beyond its own shorter remaining deadline.
            phase_engine = create_engine(source.url, creator=connect, poolclass=NullPool,
                                         execution_options=source.get_execution_options())
            event.listen(phase_engine, "before_cursor_execute", limits)
            return phase_engine
        self._make_engine = make_engine

    async def run(self, operation, *, deadline):
        """Create/use/close a Session inside one worker; return no ORM objects."""
        budget = Budget(deadline)

        def work():
            token = _budget.set(budget)
            phase_engine = self._make_engine()
            db = DeadlineSession(bind=phase_engine, expire_on_commit=False)
            db.info["assistant_deadline"] = deadline
            try:
                budget.remaining()
                result = operation(db)
                budget.remaining()
                return result
            except SQLAlchemyError as error:
                original = getattr(error, "orig", None)
                if getattr(original, "sqlstate", None) in {"55P03", "57014"}:
                    raise expired() from None
                budget.remaining()
                raise
            finally:
                try:
                    # Invalidation closes the phase's connection locally. It
                    # avoids an unbounded cleanup ROLLBACK after budget expiry.
                    if time.monotonic() >= deadline:
                        db.invalidate()
                    elif db.in_transaction():
                        db.rollback()  # Driver wait uses the SAME budget.
                finally:
                    try:
                        db.close()
                    finally:
                        try:
                            phase_engine.dispose()
                        finally:
                            _budget.reset(token)

        try:
            with anyio.fail_after(budget.remaining()):
                # Cancellation never abandons the worker. Driver deadlines end
                # I/O and close the Session before its caller releases capacity.
                result = await anyio.to_thread.run_sync(work, abandon_on_cancel=False)
            # The worker's finally has now closed the Session and disposed its
            # engine. A shielded worker may return after cancellation/deadline;
            # neither a prepared result nor a committed operation proves that
            # publication is still timely. Never relabel a commit as rollback.
            budget.remaining()
            await anyio.lowlevel.checkpoint_if_cancelled()
            budget.remaining()
            return result
        except TimeoutError:
            raise expired() from None


def get_assistant_database(request: Request):
    database = getattr(request.app.state, "assistant_database", None)
    if database is None:
        database = request.app.state.assistant_database = AssistantDatabase()
    return database
