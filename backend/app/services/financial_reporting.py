"""Complete SQL aggregates plus bounded detail projections, in the caller snapshot.

No ORM population scan, descriptions, commits or clock reads. All selectors use
explicit owner/date inputs and share the authoritative API reader expressions.
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import case, func, select

from app.models import Category, SavingsGoal, Transaction
from app.services import accounts, budgets, dashboard, goals
from app.services.assistant_contracts import GroundingContractViolation
from app.schemas.assistant import PersistedFailureCode
from app.core.financial import MAX_SAFE_PAISE


@dataclass(frozen=True)
class Comparison:
    category_id: UUID | None
    label: str
    current_paise: int
    prior_paise: int

    @property
    def delta_paise(self):return self.current_paise-self.prior_paise

    @property
    def delta_basis_points(self):
        if not self.prior_paise:return None
        value=(abs(self.delta_paise)*10000+self.prior_paise//2)//self.prior_paise
        return -value if self.delta_paise<0 else value


def comparison_ranges(as_of: date):
    start=as_of.replace(day=1);last=start-timedelta(days=1);prior=last.replace(day=1)
    end=prior.replace(day=min(as_of.day,monthrange(prior.year,prior.month)[1]))+timedelta(days=1)
    return start,as_of+timedelta(days=1),prior,end


def category_comparison_statement(*,user_id,as_of):
    start,end,prior,prior_end=comparison_ranges(as_of)
    return select(Transaction.category_id,Category.name.label('label'),
        func.sum(case((Transaction.transaction_date>=start,Transaction.amount_paise),else_=0)).label('current_paise'),
        func.sum(case((Transaction.transaction_date<prior_end,Transaction.amount_paise),else_=0)).label('prior_paise')
    ).outerjoin(Category,(Category.user_id==Transaction.user_id)&(Category.id==Transaction.category_id)).where(
        *budgets.expense_conditions(user_id=user_id,start=prior,end=end),
        (Transaction.transaction_date>=start)|(Transaction.transaction_date<prior_end)
    ).group_by(Transaction.category_id,Category.name)


def category_comparison(db,*,user_id,as_of):
    # Existing shared complete-population reader; assistant uses SQL-ranked pages
    # below so it never hydrates this unbounded result in Python.
    return tuple(Comparison(key,label or 'Uncategorized',int(current),int(prior))
                 for key,label,current,prior in db.execute(category_comparison_statement(user_id=user_id,as_of=as_of)))


def rank_comparisons(rows,*,increases=False):
    return tuple(sorted((r for r in rows if not increases or r.delta_paise>0),
        key=lambda r:(-(r.delta_paise if increases else r.current_paise),str(r.category_id or ''))))


@dataclass(frozen=True)
class ReportPage:
    items: tuple
    count: int
    totals: tuple[tuple[str,int], ...]


@dataclass(frozen=True)
class FinancialReport:
    accounts: ReportPage
    budgets: ReportPage
    goals: ReportPage
    summary: dict
    categories: ReportPage
    increases: ReportPage


def _page(db,query,*,limit,money,invalid=None):
    """Aggregate the full relation, then fetch at most limit detail records."""
    q=query.order_by(None).subquery()
    columns=[func.count()]+[func.coalesce(func.sum(q.c[name]),0) for name in money]
    if invalid is not None:columns.append(func.coalesce(func.bool_or(invalid(q)),False))
    totals=db.execute(select(*columns).select_from(q)).one()
    if invalid is not None and totals[-1]:raise GroundingContractViolation(PersistedFailureCode.FINANCIAL_INVARIANT)
    return ReportPage(tuple(db.execute(query.limit(limit)).mappings()),int(totals[0]),
                      tuple((name,int(value)) for name,value in zip(money,totals[1:])))


def read_finances(db,*,user_id: UUID,as_of: date):
    a=accounts.account_balance_statement(user_id=user_id,as_of=as_of).subquery()
    account_query=select(a.c.id,a.c.name,a.c.balance_paise,a.c.goal_allocated_paise,a.c.available_to_spend_paise,
                         a.c.opening_balance_as_of).order_by(a.c.is_default.desc(),a.c.created_at,a.c.id)
    if db.scalar(select(func.count()).select_from(a).where(a.c.opening_balance_as_of>as_of)):
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_UNAVAILABLE)
    account_page=_page(db,account_query,limit=10,money=('balance_paise','goal_allocated_paise','available_to_spend_paise'),
        invalid=lambda q:(q.c.balance_paise<0)|(q.c.balance_paise>MAX_SAFE_PAISE)|
            (q.c.goal_allocated_paise<0)|(q.c.goal_allocated_paise>MAX_SAFE_PAISE)|
            (q.c.available_to_spend_paise<0)|(q.c.available_to_spend_paise>MAX_SAFE_PAISE))
    b=budgets.month_snapshot_statement(user_id=user_id,month_start=as_of.replace(day=1)).order_by(None).subquery()
    budget_query=select(b.c.id,b.c.category_id,b.c.category_name,b.c.limit_paise,b.c.actual_spending_paise,
        (b.c.limit_paise-b.c.actual_spending_paise).label('remaining_paise')).order_by(b.c.category_id.is_not(None),b.c.category_id,b.c.id)
    budget_page=_page(db,budget_query,limit=10,money=('limit_paise','actual_spending_paise','remaining_paise'),
        invalid=lambda q:(q.c.limit_paise<=0)|(q.c.limit_paise>MAX_SAFE_PAISE))
    net=goals.allocation_statement(user_id=user_id,as_of=as_of).subquery()
    g=select(net.c.goal_id,func.sum(net.c.allocated_paise).label('allocated_paise'),
        func.bool_or(net.c.allocated_paise<0).label('invalid')).group_by(net.c.goal_id).subquery()
    allocated=func.coalesce(g.c.allocated_paise,0)
    goal_query=select(SavingsGoal.id,SavingsGoal.name,SavingsGoal.target_paise,SavingsGoal.target_date,
        allocated.label('allocated_paise'),(SavingsGoal.target_paise-allocated).label('remaining_paise'),
        func.coalesce(g.c.invalid,False).label('invalid')).outerjoin(g,g.c.goal_id==SavingsGoal.id).where(
        SavingsGoal.user_id==user_id,SavingsGoal.deleted_at.is_(None)
    ).order_by(SavingsGoal.created_at.desc(),SavingsGoal.id.desc())
    goal_page=_page(db,goal_query,limit=10,money=('target_paise','allocated_paise','remaining_paise'),
        invalid=lambda q:q.c.invalid|(q.c.target_paise<=0)|(q.c.target_paise>MAX_SAFE_PAISE)|
                         (q.c.allocated_paise<0)|(q.c.allocated_paise>MAX_SAFE_PAISE))
    c=category_comparison_statement(user_id=user_id,as_of=as_of).subquery()
    comparison_query=select(c).order_by(c.c.current_paise.desc(),c.c.category_id.asc().nullsfirst())
    category_page=_page(db,comparison_query,limit=5,money=('current_paise','prior_paise'))
    increase_query=select(c).where(c.c.current_paise>c.c.prior_paise).order_by(
        (c.c.current_paise-c.c.prior_paise).desc(),c.c.category_id.asc().nullsfirst())
    increase_page=_page(db,increase_query,limit=5,money=())
    summary=dashboard.get_dashboard_summary(db,user_id=user_id,as_of=as_of,goal_limit=10,transaction_limit=10,budget_limit=10)
    return FinancialReport(account_page,budget_page,goal_page,summary,category_page,
                           ReportPage(increase_page.items,increase_page.count,category_page.totals))
