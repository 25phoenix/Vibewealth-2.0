"""One-snapshot, tenant-scoped financial summary for the dashboard."""

from __future__ import annotations

from datetime import date
import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.financial import MAX_SAFE_PAISE, financial_today

DASHBOARD_GOAL_LIMIT = 5
DASHBOARD_TRANSACTION_LIMIT = 4


class DashboardSummaryInvariantError(RuntimeError):
    """Persisted dashboard values violate existing safe-integer invariants."""


def dashboard_month_range(financial_date: date) -> tuple[date, date]:
    """Return the inclusive month start and exclusive next-month boundary."""

    month_start = financial_date.replace(day=1)
    if month_start.month == 12:
        month_end_exclusive = date(month_start.year + 1, 1, 1)
    else:
        month_end_exclusive = date(month_start.year, month_start.month + 1, 1)
    return month_start, month_end_exclusive


_SUMMARY_SQL = text(
    """
    WITH account_transaction_net AS (
        SELECT t.user_id, t.account_id,
               SUM(CASE WHEN t.transaction_type = 'income'
                        THEN t.amount_paise ELSE -t.amount_paise END) AS net_paise
        FROM transactions AS t
        JOIN accounts AS opened_account
          ON opened_account.user_id = t.user_id
         AND opened_account.id = t.account_id
        WHERE t.user_id = :user_id
          AND t.deleted_at IS NULL
          AND t.transaction_date >= opened_account.opening_balance_as_of
          AND t.transaction_date <= :financial_date
        GROUP BY t.user_id, t.account_id
    ), account_allocation_net AS (
        SELECT ge.user_id, ge.account_id,
               SUM(CASE WHEN ge.entry_type = 'contribution'
                        THEN ge.amount_paise ELSE -ge.amount_paise END) AS net_paise
        FROM goal_entries AS ge
        WHERE ge.user_id = :user_id
          AND ge.effective_date <= :financial_date
        GROUP BY ge.user_id, ge.account_id
    ), active_accounts AS (
        SELECT a.id,
               a.opening_balance_paise + COALESCE(atn.net_paise, 0) AS balance_paise,
               COALESCE(aan.net_paise, 0) AS goal_allocated_paise,
               a.opening_balance_paise + COALESCE(atn.net_paise, 0)
                    - COALESCE(aan.net_paise, 0) AS available_to_spend_paise
        FROM accounts AS a
        LEFT JOIN account_transaction_net AS atn
          ON atn.user_id = a.user_id AND atn.account_id = a.id
        LEFT JOIN account_allocation_net AS aan
          ON aan.user_id = a.user_id AND aan.account_id = a.id
        WHERE a.user_id = :user_id AND a.archived_at IS NULL
    ), account_totals AS (
        SELECT COUNT(*) AS account_count,
               COALESCE(SUM(balance_paise), 0)::text AS balance_paise,
               COALESCE(SUM(goal_allocated_paise), 0)::text AS goal_allocated_paise,
               COALESCE(SUM(available_to_spend_paise), 0)::text AS available_to_spend_paise
        FROM active_accounts
    ), monthly_transaction_rows AS (
        SELECT t.id, t.account_id, t.category_id, t.transaction_type,
               t.amount_paise, t.description, t.transaction_date,
               t.created_at, c.name AS category_name
        FROM transactions AS t
        JOIN accounts AS opened_account
          ON opened_account.user_id = t.user_id
         AND opened_account.id = t.account_id
        LEFT JOIN categories AS c
          ON c.user_id = t.user_id
         AND c.id = t.category_id
         AND c.transaction_type = t.transaction_type
        WHERE t.user_id = :user_id
          AND t.deleted_at IS NULL
          AND t.transaction_date >= :month_start
          AND t.transaction_date < :month_end_exclusive
          AND t.transaction_date <= :financial_date
          AND t.transaction_date >= opened_account.opening_balance_as_of
    ), cash_flow AS (
        SELECT COALESCE(SUM(amount_paise) FILTER (WHERE transaction_type = 'income'), 0)::text
                   AS income_paise,
               COALESCE(SUM(amount_paise) FILTER (WHERE transaction_type = 'expense'), 0)::text
                   AS expenses_paise
        FROM monthly_transaction_rows
    ), budget_expense_rows AS (
        SELECT t.category_id, t.amount_paise
        FROM transactions AS t
        WHERE t.user_id = :user_id
          AND t.deleted_at IS NULL
          AND t.transaction_type = 'expense'
          AND t.transaction_date >= :month_start
          AND t.transaction_date < :month_end_exclusive
    ), overall_month_spending AS (
        SELECT COALESCE(SUM(amount_paise), 0) AS amount_paise
        FROM budget_expense_rows
    ), category_month_spending AS (
        SELECT category_id, SUM(amount_paise) AS amount_paise
        FROM budget_expense_rows
        GROUP BY category_id
    ), budget_rows AS (
        SELECT b.id, b.month_start, b.category_id, c.name AS category_name,
               b.limit_paise,
               CASE WHEN b.category_id IS NULL
                    THEN oms.amount_paise
                    ELSE COALESCE(cms.amount_paise, 0)
               END AS actual_spending_paise
        FROM budgets AS b
        LEFT JOIN categories AS c
          ON c.user_id = b.user_id AND c.id = b.category_id
        LEFT JOIN category_month_spending AS cms ON cms.category_id = b.category_id
        CROSS JOIN overall_month_spending AS oms
        WHERE b.user_id = :user_id AND b.month_start = :month_start
        ORDER BY b.category_id IS NOT NULL, b.category_id, b.id
        LIMIT :budget_limit
    ), goal_allocation_net AS (
        SELECT ge.goal_id, ge.account_id,
               SUM(CASE WHEN ge.entry_type = 'contribution'
                        THEN ge.amount_paise ELSE -ge.amount_paise END) AS amount_paise
        FROM goal_entries AS ge
        WHERE ge.user_id = :user_id AND ge.effective_date <= :financial_date
        GROUP BY ge.goal_id, ge.account_id
    ), goal_totals AS (
        SELECT goal_id, SUM(amount_paise) AS amount_paise,
               BOOL_OR(amount_paise < 0) AS invalid_allocation
        FROM goal_allocation_net
        GROUP BY goal_id
    ), goal_rows AS (
        SELECT g.id, g.name, g.target_date, g.target_paise,
               COALESCE(gt.amount_paise, 0) AS allocated_paise,
               COALESCE(gt.invalid_allocation, FALSE) AS invalid_allocation,
               g.created_at
        FROM savings_goals AS g
        LEFT JOIN goal_totals AS gt ON gt.goal_id = g.id
        WHERE g.user_id = :user_id AND g.deleted_at IS NULL
        ORDER BY g.created_at DESC, g.id DESC
        LIMIT :goal_limit
    ), recent_count AS (
        SELECT COUNT(*) AS total
        FROM transactions AS t
        WHERE t.user_id = :user_id AND t.deleted_at IS NULL
    ), recent_rows AS (
        SELECT t.id, t.account_id, t.category_id, c.name AS category_name,
               t.transaction_type, t.amount_paise, t.description,
               t.transaction_date, t.created_at
        FROM transactions AS t
        LEFT JOIN categories AS c
          ON c.user_id = t.user_id
         AND c.id = t.category_id
         AND c.transaction_type = t.transaction_type
        WHERE t.user_id = :user_id AND t.deleted_at IS NULL
        ORDER BY t.transaction_date DESC, t.created_at DESC, t.id DESC
        LIMIT :transaction_limit
    )
    SELECT
        :financial_date AS financial_date,
        :month_start AS month_start,
        :month_end_exclusive AS month_end_exclusive,
        (SELECT json_build_object(
            'account_count', account_count,
            'balance_paise', balance_paise,
            'goal_allocated_paise', goal_allocated_paise,
            'available_to_spend_paise', available_to_spend_paise
        ) FROM account_totals) AS account_totals,
        (SELECT json_build_object(
            'income_paise', income_paise,
            'expenses_paise', expenses_paise,
            'net_paise', (income_paise::numeric - expenses_paise::numeric)::text
        ) FROM cash_flow) AS cash_flow,
        COALESCE((SELECT json_agg(json_build_object(
            'id', id,
            'month_start', month_start,
            'category_id', category_id,
            'category_name', category_name,
            'limit_paise', limit_paise,
            'actual_spending_paise', actual_spending_paise::text,
            'remaining_paise', (limit_paise::numeric - actual_spending_paise)::text,
            'percent_used_basis_points', FLOOR(
                (actual_spending_paise * 10000 + FLOOR(limit_paise::numeric / 2))
                / limit_paise
            )::text
        ) ORDER BY category_id IS NOT NULL, category_id, id) FROM budget_rows), '[]'::json)
            AS budgets,
        COALESCE((SELECT json_agg(json_build_object(
            'id', id,
            'name', name,
            'target_date', target_date,
            'target_paise', target_paise,
            'allocated_paise', allocated_paise::text,
            'invalid_allocation', invalid_allocation
        ) ORDER BY created_at DESC, id DESC) FROM goal_rows), '[]'::json) AS goals,
        (SELECT COUNT(*) FROM savings_goals
         WHERE user_id = :user_id AND deleted_at IS NULL) AS goals_total,
        (SELECT json_build_object(
            'items', COALESCE((SELECT json_agg(json_build_object(
                'id', id,
                'account_id', account_id,
                'category_id', category_id,
                'category_name', category_name,
                'transaction_type', transaction_type,
                'amount_paise', amount_paise,
                'description', description,
                'transaction_date', transaction_date
            ) ORDER BY transaction_date DESC, created_at DESC, id DESC) FROM recent_rows), '[]'::json),
            'total', total,
            'offset', 0,
            'limit', :transaction_limit
        ) FROM recent_count) AS recent_transactions
    """
)


def get_dashboard_summary(db: Session, *, user_id: UUID, as_of: date | None = None,
                          goal_limit: int = DASHBOARD_GOAL_LIMIT,
                          transaction_limit: int = DASHBOARD_TRANSACTION_LIMIT,
                          budget_limit: int | None = None) -> dict[str, object]:
    """Read dashboard financial data from one PostgreSQL statement snapshot."""

    today = as_of or financial_today()
    month_start, month_end_exclusive = dashboard_month_range(today)

    statement = _SUMMARY_SQL
    schema_map = db.get_bind().get_execution_options().get("schema_translate_map")
    schema = schema_map.get(None) if schema_map else None
    if schema:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ValueError("Invalid translated database schema name")
        quoted_schema = f'"{schema}".'
        statement = text(
            re.sub(
                r"(\b(?:FROM|JOIN)\s+)(accounts|transactions|goal_entries|budgets|categories|savings_goals)\b",
                lambda match: f'{match.group(1)}{quoted_schema}"{match.group(2)}"',
                _SUMMARY_SQL.text,
            )
        )

    row = db.execute(
        statement,
        {
            "user_id": user_id,
            "financial_date": today,
            "month_start": month_start,
            "month_end_exclusive": month_end_exclusive,
            "goal_limit": goal_limit,
            "budget_limit": budget_limit,
            "transaction_limit": transaction_limit,
        },
    ).mappings().one()
    result = dict(row)

    for goal in result["goals"]:
        allocated = int(goal["allocated_paise"])
        target = int(goal["target_paise"])
        if (
            goal["invalid_allocation"]
            or not 0 <= allocated <= MAX_SAFE_PAISE
            or not 0 < target <= MAX_SAFE_PAISE
        ):
            raise DashboardSummaryInvariantError(
                "Stored goal allocation exceeds the supported monetary range"
            )
        goal["allocated_paise"] = allocated
        goal["remaining_target_paise"] = target - allocated
        del goal["invalid_allocation"]

    return result
