"""Immutable financial context and verified token-counting boundary.

This function requires a NEW worker-owned Session. It rejects any preexisting
transaction so ORM/autobegin cannot silently choose an earlier MVCC snapshot.
"""
from itertools import islice
from collections.abc import Sequence
import time
from datetime import date, datetime, timezone
import json
from typing import Protocol, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text

from app.models import AssistantMessage, AssistantTurn
from app.core.financial import MAX_SAFE_PAISE
from app.services.financial_reporting import read_finances, comparison_ranges, Comparison
from app.services.budgets import percent_used_basis_points
from app.services.dashboard import DashboardSummaryInvariantError
from app.services.goals import GoalAllocationInvariantError
from app.schemas.assistant import PersistedFailureCode
from app.services.assistant_contracts import GroundingContractViolation


class Fact(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', strict=True)
    id: str
    label: str
    values: tuple[tuple[str, str], ...]


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', strict=True)
    state: Literal['complete', 'empty', 'truncated']  # Failed required reads never become zero
    count: int
    totals: tuple[tuple[str, str], ...]
    items: tuple[Fact, ...]


class FinancialContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', strict=True)
    version: int = 1
    context_as_of: datetime
    financial_date: date
    intervals: tuple[tuple[str, str], ...]
    accounts: Section
    cash_flow: Section
    budgets: Section
    goals: Section
    recent_transactions: Section
    category_totals: Section
    category_increases: Section
    notices: tuple[str, ...]


def fact(key, label, **values):
    # Labels are never instructions; consumers render text, not HTML/markdown.
    return Fact(id=str(key), label=str(label)[:100], values=tuple((k, str(v)) for k, v in values.items()))


def section(items, **totals):
    items=tuple(islice(items,11))
    if len(items)>10:raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
    return Section(state='complete' if items else 'empty',count=len(items),
        totals=tuple((k,str(v)) for k,v in totals.items()),items=items)


def bounded(items, limit, *, total_count=None, **totals):
    # Caller supplies SQL count, or a bounded Sequence with an O(1) length.
    # Never consume an unknown-length generator to discover its population.
    if total_count is None:
        if not isinstance(items,Sequence):raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
        total_count=len(items)
    rows=tuple(islice(items,limit))
    if total_count<len(rows):raise GroundingContractViolation(PersistedFailureCode.FINANCIAL_INVARIANT)
    return Section(state='truncated' if total_count>len(rows) else ('complete' if rows else 'empty'),
        count=total_count,totals=tuple((k,str(v)) for k,v in totals.items()),items=rows)


def _check_budget(db):
    deadline=db.info.get('assistant_deadline')
    if deadline is not None and time.monotonic()>=deadline:
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_UNAVAILABLE)


def build_context(db, *, user_id: UUID):
    _check_budget(db)
    if db.in_transaction():
        raise ValueError('Financial reporting requires a fresh transaction')
    db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
    db.execute(text('SET TRANSACTION READ ONLY'))
    # This MUST remain the first snapshot-taking statement, before ORM queries.
    snapshot = db.execute(text('SELECT pg_current_snapshot() AS snapshot_id, clock_timestamp() AS observed_at')).one()
    observed = snapshot.observed_at.astimezone(timezone.utc)
    as_of = observed.astimezone(ZoneInfo('Asia/Kolkata')).date()
    try:
        report=read_finances(db,user_id=user_id,as_of=as_of)
        _check_budget(db)
        account_totals=dict(report.accounts.totals)
        account_section=bounded((fact(a['id'],a['name'],balance_paise=a['balance_paise'],
            allocated_paise=a['goal_allocated_paise'],available_paise=a['available_to_spend_paise']) for a in report.accounts.items),
            10,total_count=report.accounts.count,balance_paise=account_totals['balance_paise'],
            allocated_paise=account_totals['goal_allocated_paise'],available_paise=account_totals['available_to_spend_paise'])
        budget_section=bounded((fact(b['id'],b['category_name'] or 'Overall',limit_paise=b['limit_paise'],
            spending_paise=b['actual_spending_paise'],remaining_paise=b['remaining_paise'],
            used_basis_points=percent_used_basis_points(int(b['actual_spending_paise']),int(b['limit_paise'])))
            for b in report.budgets.items),10,total_count=report.budgets.count,**dict(report.budgets.totals))
        goal_section=bounded((fact(g['id'],g['name'],target_paise=g['target_paise'],allocated_paise=g['allocated_paise'],
            remaining_paise=g['remaining_paise'],target_date=g['target_date'] or 'No target date') for g in report.goals.items),
            10,total_count=report.goals.count,**dict(report.goals.totals))
        recent=report.summary['recent_transactions']
        recent_section=bounded((fact(t['id'],t['transaction_type'],amount_paise=t['amount_paise'],date=t['transaction_date'])
            for t in recent['items']),10,total_count=recent['total'])
        def comparison_section(page):
            def examples():
                for c in page.items:
                    comparison=Comparison(c['category_id'],c['label'] or 'Uncategorized',int(c['current_paise']),int(c['prior_paise']))
                    yield fact(comparison.category_id or 'uncategorized',comparison.label,current_paise=comparison.current_paise,
                        prior_paise=comparison.prior_paise,delta_paise=comparison.delta_paise,
                        delta_basis_points=comparison.delta_basis_points if comparison.delta_basis_points is not None else 'no prior spending')
            return bounded(examples(),5,total_count=page.count,**dict(page.totals))
        start, end, previous, previous_end = comparison_ranges(as_of)
        notices = ['Recorded data may be incomplete. Missing imports, recurring obligations and future income are unknown. '
                   'I cannot create, edit or delete financial records; use the normal authenticated screens. '
                   'Budget totals may overlap when overall and category budgets coexist. Available-to-spend does not guarantee affordability. Goal allocations are virtual reservations, not expenses or transfers.']
        if (end-start).days != (previous_end-previous).days:
            notices.append('Comparison periods contain unequal numbers of days.')
        result = FinancialContext(context_as_of=observed, financial_date=as_of,
            intervals=(('current_start', str(start)), ('current_end_exclusive', str(end)),
                       ('prior_start', str(previous)), ('prior_end_exclusive', str(previous_end))),
            accounts=account_section, cash_flow=section([fact('month', 'Month cash flow', **report.summary['cash_flow'])]),
            budgets=budget_section, goals=goal_section, recent_transactions=recent_section,
            category_totals=comparison_section(report.categories), category_increases=comparison_section(report.increases), notices=tuple(notices))
        _check_budget(db)
        db.commit()  # No reporting transaction can span provider I/O.
        return result
    except BaseException:
        db.rollback()
        raise


def completed_history(db, *, user_id: UUID, conversation_id: UUID):
    turns = list(db.scalars(select(AssistantTurn).where(AssistantTurn.user_id == user_id,
        AssistantTurn.conversation_id == conversation_id, AssistantTurn.status == 'completed')
        .order_by(AssistantTurn.user_sequence_no.desc()).limit(6)))
    positions = [p for t in turns for p in (t.user_sequence_no, t.assistant_sequence_no)]
    return tuple((m.role, m.content) for m in db.scalars(select(AssistantMessage).where(
        AssistantMessage.user_id == user_id, AssistantMessage.conversation_id == conversation_id,
        AssistantMessage.sequence_no.in_(positions)).order_by(AssistantMessage.sequence_no)))


class VerifiedTokenCounter(Protocol):
    """Counts exact serialized request AND reserved output for this model/template.

    Implementations require actual-machine benchmark verification; a character
    heuristic or a count from a different tokenizer/model is not supported.
    """
    def count_request(self, request: bytes, *, reserved_output: int) -> int: ...


def encode_model_request(payload, counter: VerifiedTokenCounter | None):
    import asyncio
    try:asyncio.get_running_loop()
    except RuntimeError:pass
    else:raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
    wire = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    if counter is None:
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
    try:
        count = counter.count_request(wire, reserved_output=512)
    except Exception:
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT) from None
    if type(count) is not int or not 0 < count <= 16384:
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
    return wire


async def prepare_context(database, *, user_id: UUID, conversation_id: UUID, deadline: float):
    """Worker-owned five-second reporting phase, capped by the original budget.

    All financial reads share the required read-only snapshot. Completed history
    is a separate bounded read of untrusted stale text, never financial evidence.
    Neither ORM rows nor the session escape the worker.
    """
    import time
    from app.schemas.assistant import HttpErrorCode
    from app.services.assistant_contracts import ContractViolation
    from sqlalchemy.exc import SQLAlchemyError
    def prepare(db):
        # build_context closes its transaction; history is deliberately not
        # current financial evidence and has a separate bounded read-only scope.
        context = build_context(db, user_id=user_id)
        history = completed_history(db, user_id=user_id, conversation_id=conversation_id)
        db.rollback()
        return context, history
    try:
        return await database.run(prepare, deadline=min(deadline, time.monotonic()+5))
    except GroundingContractViolation:
        raise
    except ContractViolation as error:
        if error.code == HttpErrorCode.AUTHENTICATION_REQUIRED:
            raise
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_UNAVAILABLE) from None
    except (
        DashboardSummaryInvariantError,
        GoalAllocationInvariantError,
    ):
        raise GroundingContractViolation(PersistedFailureCode.FINANCIAL_INVARIANT) from None
    except (SQLAlchemyError, ValueError, RuntimeError):
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_UNAVAILABLE) from None
