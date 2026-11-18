"""Backend-authored complete claims. Provider bytes select IDs, never prose.

Entity labels are escaped text and never interpreted as markup or instructions.
Mandatory coverage notices are appended outside provider selection.
"""
from dataclasses import dataclass
from html import escape

from app.schemas.assistant import Topic, PersistedFailureCode
from app.services.assistant_contracts import (
    GroundingContractViolation, parse_provider_output, validate_claim_selection,
)
from app.services.assistant_context import FinancialContext

SCOPE = ('I can summarize your recorded accounts, transactions, budgets and goals. '
         'I cannot execute financial actions, provide unrestricted financial advice or answer unrelated questions. '
         'Use the normal authenticated screens to create, edit or delete financial records.')


def inr(value: str):
    amount = int(value)
    sign = '-' if amount < 0 else ''
    whole, fraction = divmod(abs(amount), 100)
    return f'{sign}₹{whole:,}.{fraction:02d}'


def percentage(value: str):
    amount = int(value)
    sign = '-' if amount < 0 else ''
    whole, fraction = divmod(abs(amount), 100)
    return f'{sign}{whole}.{fraction:02d}%'


@dataclass(frozen=True)
class Claim:
    id: str
    topics: frozenset[Topic]
    text: str
    order: int
    coverage: str


@dataclass(frozen=True)
class Catalog:
    claims: tuple[Claim, ...]
    baselines: tuple[tuple[Topic, frozenset[str]], ...]
    exclusive_groups: tuple[frozenset[str], ...] = ()
    truncated: bool = False


def build_catalog(context: FinancialContext):
    claims = []
    required = {}
    def add(key, topic, text, coverage, *, baseline=False):
        claims.append(Claim(key, frozenset([topic]), text, len(claims), coverage))
        if baseline:
            required[topic] = frozenset([key])
    accounts = dict(context.accounts.totals)
    cash = dict(context.cash_flow.items[0].values)
    add('summary.baseline', Topic.SUMMARY,
        f'Recorded active accounts: {context.accounts.count}; current-month budgets: {context.budgets.count}; '
        f'active savings goals: {context.goals.count}.', 'accounts,budgets,goals', baseline=True)
    for topic in (Topic.ACCOUNTS, Topic.AFFORDABILITY_CONTEXT):
        add(f'{topic.value}.baseline', topic,
            f'Active-account balance is {inr(accounts["balance_paise"])}; net goal allocations are '
            f'{inr(accounts["allocated_paise"])}; available-to-spend is {inr(accounts["available_paise"])}. '
            'Allocations have already been subtracted once.', 'accounts', baseline=True)
    add('cash_flow.baseline', Topic.CASH_FLOW,
        f'Current-month cash flow through {context.financial_date}: income {inr(cash["income_paise"])}, '
        f'expenses {inr(cash["expenses_paise"])}, net {inr(cash["net_paise"])}. '
        'Cash flow includes owned archived accounts and respects account opening dates.', 'cash_flow', baseline=True)
    totals = dict(context.category_totals.totals)
    add('spending.baseline', Topic.SPENDING,
        f'Recorded month-to-date expenses are {inr(totals["current_paise"])}. '
        'Recorded expense reporting has no account-opening-date cutoff.', 'category_totals', baseline=True)
    add('budgets.baseline', Topic.BUDGETS,
        f'There are {context.budgets.count} current-month budgets. Budget spending covers the full calendar month, '
        'including uncategorized expenses for overall budgets; income and allocations are excluded. '
        'No budget does not mean unlimited spending.', 'budgets', baseline=True)
    add('goals.baseline', Topic.GOALS,
        f'There are {context.goals.count} active goals; allocated total is '
        f'{inr(dict(context.goals.totals)["allocated_paise"])}. Contributions reserve money virtually; '
        'they are not expenses or transfers and do not change actual account balances.', 'goals', baseline=True)
    periods = dict(context.intervals)
    add('category_comparison.baseline', Topic.CATEGORY_COMPARISON,
        f'Recorded expense intervals are [{periods["current_start"]}, {periods["current_end_exclusive"]}) '
        f'and [{periods["prior_start"]}, {periods["prior_end_exclusive"]}). '
        f'Full-population totals are {inr(totals["current_paise"])} and {inr(totals["prior_paise"])}. '
        'Archived and uncategorized categories are included.', 'category_totals', baseline=True)
    add('recent_transactions.baseline', Topic.RECENT_TRANSACTIONS,
        f'There are {context.recent_transactions.count} recorded live transactions. '
        'Recent records are a bounded subset, not complete spending history.', 'recent_transactions', baseline=True)
    for section_name, topic in (('accounts', Topic.ACCOUNTS), ('budgets', Topic.BUDGETS), ('goals', Topic.GOALS),
                                ('recent_transactions', Topic.RECENT_TRANSACTIONS),
                                ('category_totals', Topic.CATEGORY_COMPARISON),
                                ('category_increases', Topic.CATEGORY_COMPARISON)):
        section = getattr(context, section_name)
        for item in section.items:
            # All values originate in typed backend facts, no provider arguments.
            pieces = []
            for key, value in item.values:
                if key.endswith('_paise'):
                    rendered = inr(value)
                elif key.endswith('_basis_points') and value != 'no prior spending':
                    rendered = percentage(value)
                else:
                    rendered = escape(value)
                pieces.append(f'{key.replace("_", " ")}: {rendered}')
            add(f'{section_name}.{item.id}', topic, f'{escape(item.label)} — ' + '; '.join(pieces) + '.', section_name)
    # 9 baselines + 10+10+10+10+5+5 details = 59, below 64.
    if len(claims) > 64 or set(required) != set(Topic) - {Topic.UNSUPPORTED}:
        raise GroundingContractViolation(PersistedFailureCode.OUTPUT_REJECTED)
    return Catalog(tuple(claims), tuple(required.items()))


def render_selection(body: bytes, context: FinancialContext, catalog: Catalog):
    output = parse_provider_output(body)
    validate_claim_selection(output, allowed_topics={c.id: c.topics for c in catalog.claims},
        required_ids=dict(catalog.baselines), exclusive_groups=catalog.exclusive_groups)
    if output.topic == Topic.UNSUPPORTED:
        return SCOPE
    selected = set(output.claim_ids)
    text = '\n'.join(c.text for c in sorted(catalog.claims, key=lambda c: c.order) if c.id in selected)
    notices = [f'Observed at {context.context_as_of.isoformat()} from a consistent database snapshot; '
               f'financial date {context.financial_date} (Asia/Kolkata).', *context.notices]
    if catalog.truncated:
        notices.append('Optional detail claims were omitted to fit the model context budget.')
    for field in ('accounts', 'budgets', 'goals', 'recent_transactions', 'category_totals', 'category_increases'):
        section = getattr(context, field)
        if section.state in {'empty', 'truncated'}:
            notices.append(f'{field.replace("_", " ").capitalize()}: {section.state}; '
                           f'{len(section.items)} of {section.count} detail records shown in context.')
    result = text + '\n\n' + '\n'.join(notices)
    # Rendering has its own hard bound; token accounting covers mandatory
    # templates/notices before inference, never truncate a selected claim.
    if len(result.encode('utf-8')) > 16000:
        raise GroundingContractViolation(PersistedFailureCode.CONTEXT_LIMIT)
    return result
