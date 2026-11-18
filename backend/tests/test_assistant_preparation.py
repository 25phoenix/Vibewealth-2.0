"""Preparation refusal and real orchestration cancellation; no DB/model/network."""
import time
from uuid import UUID

import anyio
import pytest

from app.core.assistant_admission import AssistantAdmission
from app.services.assistant_contracts import GroundingContractViolation
from app.services.assistant_preparation import PreparationRun,TestProcessCounter,prepare_selection_async,counter_supported
from tests.test_assistant_reporting import context


def test_unknown_counter_is_rejected_without_ever_calling_it():
    class Unsupported:
        def count_request(self,*args,**kwargs):raise AssertionError('Unsafe callback entered')
    counter=Unsupported()
    assert not counter_supported(counter,test_environment=True)
    assert not counter_supported(TestProcessCounter(),test_environment=False)
    async def run():
        with pytest.raises(GroundingContractViolation):
            await prepare_selection_async(context(),content='Test',history=(),counter=counter,deadline=time.monotonic()+1,test_environment=True)
    anyio.run(run)


@pytest.mark.parametrize("phase", ["serialization", "startup", "reap"])
@pytest.mark.parametrize("expired", [False, True])
def test_unsupported_preparation_never_enters_potentially_blocked_phase(monkeypatch, phase, expired):
    """Refusal proof, NOT a claim that native startup/reap can be timed out."""
    import asyncio
    entered = []
    class UnsafeInput:
        def model_dump(self, **kwargs):
            entered.append("serialization")
            raise AssertionError("Unsupported serialization entered")
    blocked = anyio.Event()
    async def unsafe_phase(*args, **kwargs):
        entered.append(phase)
        await blocked.wait()  # Intentionally never released: refusal must precede it.
    class UnsafeObserver:
        async def run(self, *args, **kwargs):
            entered.append("reap")
            await anyio.sleep_forever()
    if phase == "serialization":
        monkeypatch.setattr(anyio.to_thread, "run_sync", unsafe_phase)
    elif phase == "startup":
        monkeypatch.setattr(asyncio, "create_subprocess_exec", unsafe_phase)
    else:
        monkeypatch.setattr(asyncio.subprocess.Process, "wait", unsafe_phase)
    async def run():
        deadline = time.monotonic() + (-1 if expired else 1)
        assert not counter_supported(TestProcessCounter(), test_environment=True)
        with anyio.fail_after(1):
            with pytest.raises(GroundingContractViolation):
                await prepare_selection_async(UnsafeInput(), content="Test", history=(),
                    counter=TestProcessCounter(), deadline=deadline, test_environment=True,
                    observation=UnsafeObserver())
            with pytest.raises(GroundingContractViolation):
                await PreparationRun().run(b"{}", deadline=deadline)
        assert not entered  # No owned work exists to detach, join or release early.
    anyio.run(run)


def test_retired_worker_refuses_without_reading_or_logging_input(monkeypatch):
    from app.services import assistant_preparation_worker as worker
    import sys
    class ForbiddenIO:
        def __getattr__(self, name):raise AssertionError("Retired worker attempted IO")
    monkeypatch.setattr(sys, "stdin", ForbiddenIO())
    with pytest.raises(SystemExit) as error:worker.main()
    assert error.value.code == 2


@pytest.mark.parametrize("disconnect", [False, True])
def test_real_generate_boundary_cancels_preparation_before_capacity_release(monkeypatch, disconnect):
    """Real orchestration + ASGI receive; fake DB phases, no persistence claim.

    The guarded handler test separately asserts durable PostgreSQL recovery.
    The sealed fake owns only an async gate, never a process or real counter.
    """
    from types import SimpleNamespace
    from app.services import assistant_turns as turns
    from app.services.assistant_contracts import ContractViolation
    from app.schemas.assistant import HttpErrorCode
    owner, conversation, key = UUID(int=1), UUID(int=2), UUID(int=3)
    executor = turns.TestExecutor(preparation_paused=True)
    admission = AssistantAdmission()
    state = {"reserved": False, "dispatch": False, "complete": False}
    class Database:
        async def run(self, operation, *, deadline):
            return operation(self)
        def commit(self):pass
    authenticated = SimpleNamespace(current_user=SimpleNamespace(user_id=owner))
    monkeypatch.setattr(turns, "reauthenticate", lambda *args: None)
    monkeypatch.setattr(turns, "_admission_state", lambda *args, **kwargs: (None, None))
    def reserve(*args):
        state["reserved"] = True
        return SimpleNamespace(user_id=owner, id=UUID(int=4), attempt_no=1, attempt_started_at=None)
    monkeypatch.setattr(turns, "_new_turn", reserve)
    monkeypatch.setattr(turns.conversations, "owned_conversation", lambda *args, **kwargs: SimpleNamespace())
    def dispatch(*args):state["dispatch"] = True
    def complete(*args):state["complete"] = True
    monkeypatch.setattr(turns, "dispatch_fence", dispatch)
    monkeypatch.setattr(turns, "complete", complete)
    async def run():
        signal = anyio.Event()
        responses = []
        async def receive():
            await signal.wait()
            return {"type": "http.disconnect"}
        from app.core.assistant_admission import GenerationTicket
        original_close = GenerationTicket.close
        def close(ticket):
            assert executor.preparation_terminated.is_set()
            assert not executor.preparation_release._waiters
            return original_close(ticket)
        monkeypatch.setattr('app.core.assistant_admission.GenerationTicket.close', close)
        async def request():
            try:
                await turns.generate(Database(), authenticated, conversation, admission=admission,
                    executor=executor, test_environment=True, deadline=time.monotonic()+0.5,
                    key=key, content="Test", receive=receive)
                responses.append("late success")
            except ContractViolation as error:responses.append(error.code)
            except TimeoutError:responses.append("deadline")
        async with anyio.create_task_group() as group:
            group.start_soon(request)
            await executor.preparation_entered.wait_until(time.monotonic()+1)
            assert state["reserved"] and admission._active
            if disconnect:signal.set()
        assert executor.preparation_terminated.is_set()
        assert not executor.calls and not state["dispatch"] and not state["complete"]
        assert not admission._active and not any(admission._events.values())
        assert responses == ([HttpErrorCode.WORK_DEADLINE_EXCEEDED] if disconnect else ["deadline"])
    anyio.run(run)


def test_bounded_does_not_consume_population_to_find_count():
    from app.services.assistant_context import bounded,fact
    calls=[]
    def population():
        for i in range(1000000):calls.append(i);yield fact(str(i),'label',amount_paise=1)
    result=bounded(population(),10,total_count=1000000,amount_paise=1000000)
    assert len(calls)==10 and len(result.items)==10 and result.count==1000000
    assert dict(result.totals)['amount_paise']=='1000000' and result.state=='truncated'
    with pytest.raises(GroundingContractViolation):bounded(population(),10)


def test_expired_context_budget_cannot_start_financial_read():
    from app.services.assistant_context import _check_budget
    class Session:info={'assistant_deadline':time.monotonic()-1}
    with pytest.raises(GroundingContractViolation):_check_budget(Session())


def test_sync_preparation_and_counter_helpers_fail_closed_on_asgi_loop():
    from app.services.assistant_orchestrator import prepare_selection
    from app.services.assistant_context import encode_model_request
    class Unsafe:
        def count_request(self,*args,**kwargs):raise AssertionError('Must not run on loop')
    async def run():
        with pytest.raises(GroundingContractViolation):prepare_selection(context(),content='Test',history=(),counter=Unsafe())
        with pytest.raises(GroundingContractViolation):encode_model_request({},Unsafe())
    anyio.run(run)


def test_refused_transport_cannot_consume_a_dispatched_quota_or_leak_capacity():
    from app.services.assistant_provider import ApprovedLocalTarget,LocalSelectionProvider
    from app.services.assistant_orchestrator import GroundedExecution
    from app.services.assistant_turns import _execute,ExecutionAttempt
    from app.services.assistant_contracts import ContractViolation
    from app.schemas.assistant import ProviderKind,HttpErrorCode
    provider=LocalSelectionProvider(ApprovedLocalTarget(ProviderKind.OLLAMA,'unselected-model','http://127.0.0.1:11434',
        frozenset([('127.0.0.1',11434)])))
    executor=GroundedExecution(provider,TestProcessCounter(),deployment_approved=True)
    assert not executor.supports_execution(test_environment=True)
    admission=AssistantAdmission();ticket,_=admission.reserve_quota('owner');assert ticket.acquire_capacity()
    async def run():
        try:
            with pytest.raises(ContractViolation) as error:
                await _execute(executor,ExecutionAttempt(UUID(int=1),UUID(int=2),UUID(int=3),1),time.monotonic()+1,None,ticket)
            assert error.value.code==HttpErrorCode.PROVIDER_CONFIGURATION_INVALID
            assert not ticket.started and provider.termination_complete.is_set()
        finally:ticket.close()
    anyio.run(run)
    assert not admission._active and not any(admission._events.values())
