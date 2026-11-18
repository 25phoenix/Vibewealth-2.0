"""Reporting tests run ONLY in the existing guarded disposable schema fixture."""
from datetime import timedelta

from sqlalchemy import func, select

from app.models import Account, Transaction
from app.services import accounts, budgets, dashboard
from app.services.assistant_context import build_context
from app.services import assistant_context
from tests.test_assistant_conversations_postgres import world  # noqa: F401
from tests.test_assistant_conversations import no_application_database  # noqa: F401


def seed(world):
    with world.factory() as db:
        day=db.scalar(select(func.clock_timestamp())).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Kolkata')).date()
        account=Account(user_id=world.first.id,name='Test account',account_type='bank',
            opening_balance_paise=10000,opening_balance_as_of=day-timedelta(days=30))
        db.add(account);db.flush();identifier=account.id;db.commit()
    return day,identifier


def test_context_matches_authoritative_domain_readers_and_omits_descriptions(world):
    day,account=seed(world)
    with world.factory() as db:
        db.add(Transaction(user_id=world.first.id,account_id=account,category_id=None,
            transaction_type='expense',amount_paise=100,transaction_date=day,description='PRIVATE DO NOT INCLUDE'))
        db.commit()
    with world.factory() as db:
        result=build_context(db,user_id=world.first.id)
        assert not db.in_transaction()
    with world.factory() as db:
        authoritative=accounts._account_balance_query(db,user_id=world.first.id,as_of=result.financial_date)
        assert dict(result.accounts.totals)['balance_paise']==str(sum(b for _,b,_,_ in authoritative))
        assert len(budgets.list_budgets(db,user_id=world.first.id,month_start=day.replace(day=1)))==result.budgets.count
        summary=dashboard.get_dashboard_summary(db,user_id=world.first.id,as_of=result.financial_date)
        assert dict(result.cash_flow.items[0].values)==summary['cash_flow']
    assert 'PRIVATE' not in result.model_dump_json()
    assert result.category_totals.items[0].id=='uncategorized'


def test_exact_snapshot_statement_precedes_all_financial_reads_and_excludes_concurrent_commit(world,monkeypatch):
    day,account=seed(world)
    read=assistant_context.read_finances
    statements=[]
    def read_after_concurrent_commit(db,**kwargs):
        with world.factory() as other:
            other.add(Transaction(user_id=world.first.id,account_id=account,category_id=None,
                transaction_type='expense',amount_paise=100,transaction_date=day))
            other.commit()
        return read(db,**kwargs)
    monkeypatch.setattr(assistant_context,'read_finances',read_after_concurrent_commit)
    from sqlalchemy import event
    with world.factory() as db:
        event.listen(db.get_bind(),'before_cursor_execute',lambda conn,cursor,sql,*args: statements.append(sql))
        result=build_context(db,user_id=world.first.id)
    assert statements[0]=='SET TRANSACTION READ ONLY'
    assert statements[1]=='SELECT pg_current_snapshot() AS snapshot_id, clock_timestamp() AS observed_at'
    assert dict(result.accounts.totals)['balance_paise']=='10000'
    assert result.recent_transactions.count==0
    monkeypatch.setattr(assistant_context,'read_finances',read)
    with world.factory() as db:
        later=build_context(db,user_id=world.first.id)
    assert dict(later.accounts.totals)['balance_paise']=='9900'
    assert later.recent_transactions.count==1


def test_reporting_rejects_an_existing_autobegin_snapshot(world):
    with world.factory() as db:
        db.execute(select(1))
        import pytest
        with pytest.raises(ValueError,match='fresh transaction'):build_context(db,user_id=world.first.id)


def test_report_preserves_archived_uncategorized_deleted_budget_and_allocation_rules(world):
    from datetime import date,datetime,timezone
    from app.models import Budget,Category,GoalEntry,SavingsGoal
    from app.services.financial_reporting import read_finances
    day=date(2026,3,20); archived=datetime(2026,3,1,tzinfo=timezone.utc)
    with world.factory() as db:
        active=Account(user_id=world.first.id,name='Active',account_type='bank',opening_balance_paise=10000,
            opening_balance_as_of=date(2026,3,10))
        old=Account(user_id=world.first.id,name='Archived',account_type='cash',opening_balance_paise=1000,
            opening_balance_as_of=date(2026,1,1),archived_at=archived)
        category=Category(user_id=world.first.id,name='Archived category',transaction_type='expense',archived_at=archived)
        goal=SavingsGoal(user_id=world.first.id,name='Overfunded goal',description='PRIVATE',target_paise=50)
        db.add_all([active,old,category,goal]);db.flush()
        db.add_all([
            Transaction(user_id=world.first.id,account_id=active.id,category_id=None,transaction_type='expense',amount_paise=200,transaction_date=date(2026,3,1)),
            Transaction(user_id=world.first.id,account_id=active.id,category_id=category.id,transaction_type='expense',amount_paise=300,transaction_date=day),
            Transaction(user_id=world.first.id,account_id=old.id,category_id=None,transaction_type='expense',amount_paise=400,transaction_date=day),
            Transaction(user_id=world.first.id,account_id=active.id,category_id=None,transaction_type='expense',amount_paise=500,transaction_date=date(2026,3,31)),
            Transaction(user_id=world.first.id,account_id=active.id,category_id=None,transaction_type='expense',amount_paise=999,transaction_date=day,deleted_at=archived),
            Budget(user_id=world.first.id,category_id=None,month_start=day.replace(day=1),limit_paise=100),
            GoalEntry(user_id=world.first.id,goal_id=goal.id,account_id=active.id,entry_type='contribution',amount_paise=100,effective_date=day),
            GoalEntry(user_id=world.first.id,goal_id=goal.id,account_id=active.id,entry_type='withdrawal',amount_paise=20,effective_date=day),
        ]);db.commit()
    with world.factory() as db:
        report=read_finances(db,user_id=world.first.id,as_of=day)
    assert report.accounts.count==1 and tuple(dict(report.accounts.totals).values())==(9700,80,9620)
    assert int(report.budgets.items[0]['actual_spending_paise'])==1400 and int(report.budgets.items[0]['remaining_paise'])==-1300
    assert report.summary['cash_flow']['expenses_paise']=='700'
    assert int(report.goals.items[0]['allocated_paise'])==80 and int(report.goals.items[0]['remaining_paise'])==-30
    assert dict(report.categories.totals)['current_paise']==900
    assert any(c['label']=='Archived category' for c in report.categories.items)


def test_unverified_transport_and_counter_cannot_reserve_even_with_approval_flag(world):
    import httpx,json
    from app.services.assistant_provider import ApprovedLocalTarget,LocalSelectionProvider
    from app.services.assistant_orchestrator import GroundedExecution
    from app.services.assistant_turns import get_test_executor
    from app.schemas.assistant import ProviderKind
    from app.models import GoalEntry
    day,account=seed(world)
    class Counter:
        def count_request(self,request,*,reserved_output):return 1000  # Test-only, NOT benchmark evidence.
    class Stream:
        def get_extra_info(self,key):return ('127.0.0.1',11434)
    requests=[]
    def respond(request):
        payload=json.loads(request.content);requests.append(payload)
        return httpx.Response(200,json={'response':'{"version":1,"topic":"accounts","claim_ids":["accounts.baseline"]}'},
            extensions={'network_stream':Stream()})
    provider=LocalSelectionProvider(ApprovedLocalTarget(ProviderKind.OLLAMA,'test-present-model','http://127.0.0.1:11434',
        frozenset([('127.0.0.1',11434)])),transport=httpx.MockTransport(respond))
    # Explicit TEST composition only. This attestation cannot configure startup.
    executor=GroundedExecution(provider,Counter(),deployment_approved=True)
    world.app.dependency_overrides[get_test_executor]=lambda:executor
    conversation=world.seed_conversation()
    from uuid import uuid4
    with world.client() as client:
        result=client.post(f'/api/assistant/conversations/{conversation}/messages',json={'content':'Show recorded accounts'},
            headers={'Idempotency-Key':str(uuid4())})
    assert result.status_code==503 and result.json()['code']=='PROVIDER_CONFIGURATION_INVALID'
    assert not requests and provider.termination_complete.is_set()
    from app.models import AssistantTurn,AssistantMessage
    with world.factory() as db:
        assert db.scalar(select(func.count()).select_from(AssistantTurn))==0
        assert db.scalar(select(func.count()).select_from(AssistantMessage))==0
        assert db.scalar(select(func.count()).select_from(Transaction))==0
        assert db.scalar(select(func.count()).select_from(GoalEntry))==0


def test_worker_timeout_setup_does_not_establish_an_earlier_reporting_snapshot(world,monkeypatch):
    import anyio,time
    day,account=seed(world)
    read=assistant_context.read_finances
    def concurrent(db,**kwargs):
        with world.factory() as other:
            other.add(Transaction(user_id=world.first.id,account_id=account,category_id=None,
                transaction_type='expense',amount_paise=123,transaction_date=day))
            other.commit()
        return read(db,**kwargs)
    monkeypatch.setattr(assistant_context,'read_finances',concurrent)
    # The real C4 driver/statement-limit helper is active in this worker phase.
    result=anyio.run(lambda:world.app.state.assistant_database.run(
        lambda db:build_context(db,user_id=world.first.id),deadline=time.monotonic()+5))
    assert dict(result.accounts.totals)['balance_paise']=='10000'
    assert result.recent_transactions.count==0


def test_large_population_keeps_complete_totals_and_bounded_detail_queries(world):
    from app.models import SavingsGoal,Budget,Category
    from app.services.financial_reporting import read_finances
    day,account=seed(world)
    with world.factory() as db:
        db.add_all([SavingsGoal(user_id=world.first.id,name=f'Goal {i}',description='must never hydrate',target_paise=100)
                    for i in range(1500)])
        for i in range(25):
            category=Category(user_id=world.first.id,name=f'Expense {i}',transaction_type='expense');db.add(category);db.flush()
            db.add(Budget(user_id=world.first.id,category_id=category.id,month_start=day.replace(day=1),limit_paise=1000))
            db.add(Transaction(user_id=world.first.id,account_id=account,category_id=category.id,
                transaction_type='expense',amount_paise=i+1,transaction_date=day))
        db.commit()
    with world.factory() as db:
        report=read_finances(db,user_id=world.first.id,as_of=day)
        assert report.goals.count==1500 and len(report.goals.items)==10
        assert dict(report.goals.totals)['target_paise']==150000
        assert all('description' not in item for item in report.goals.items)
        assert report.budgets.count==25 and len(report.budgets.items)==10
        assert report.categories.count==25 and len(report.categories.items)==5
        assert dict(report.categories.totals)['current_paise']==325
        assert [int(c['current_paise']) for c in report.categories.items]==[25,24,23,22,21]
        assert len(report.summary['budgets'])==10
