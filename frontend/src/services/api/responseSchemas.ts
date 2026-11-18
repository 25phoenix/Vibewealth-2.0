import { ApiContractError } from './apiClient'
import type {
  AccountBalanceDto,
  AccountDto,
  ApiAccountType,
  ApiCategoryTransactionType,
  BudgetDto,
  DashboardSummaryDto,
  AuthUserDto,
  CategoryDto,
  CsrfTokenDto,
  GoalDto,
  GoalAccountSummaryDto,
  GoalEntryDto,
  GoalEntryListDto,
  GoalListDto,
  GoalMoneyMutationDto,
  TransactionDto,
  TransactionListDto,
} from '@/types/api'
import { isValidDateKey } from '@/lib/format'
import { API_ACCOUNT_TYPES, API_CATEGORY_TRANSACTION_TYPES } from '@/types/api'

type JsonObject = Record<string, unknown>

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isUuid(value: unknown): value is string {
  return typeof value === 'string'
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

function isDate(value: unknown): value is string {
  return typeof value === 'string' && isValidDateKey(value)
}

function isTimestamp(value: unknown): value is string {
  return typeof value === 'string'
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
    && Number.isFinite(Date.parse(value))
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isSafeInteger(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value)
}

function isDecimalIntegerString(value: unknown, allowNegative = false): value is string {
  return typeof value === 'string'
    && (allowNegative ? /^-?(?:0|[1-9]\d*)$/ : /^(?:0|[1-9]\d*)$/).test(value)
}

function invalid(contract: string): never {
  throw new ApiContractError(contract)
}

export function parseAuthUserDto(value: unknown): AuthUserDto {
  if (!isObject(value)
    || !isUuid(value.id)
    || !isNonEmptyString(value.email)
    || !(value.display_name === null || typeof value.display_name === 'string')) {
    return invalid('authentication user')
  }
  return { id: value.id, email: value.email, display_name: value.display_name }
}

export function parseCsrfTokenDto(value: unknown): CsrfTokenDto {
  if (!isObject(value) || !isNonEmptyString(value.csrf_token)) return invalid('CSRF token')
  return { csrf_token: value.csrf_token }
}

const accountTypes: ReadonlySet<string> = new Set(API_ACCOUNT_TYPES)
const categoryTransactionTypes: ReadonlySet<string> = new Set(API_CATEGORY_TRANSACTION_TYPES)

function isAccountType(value: unknown): value is ApiAccountType {
  return typeof value === 'string' && accountTypes.has(value)
}

function isCategoryTransactionType(value: unknown): value is ApiCategoryTransactionType {
  return typeof value === 'string' && categoryTransactionTypes.has(value)
}

export function parseAccountDto(value: unknown): AccountDto {
  if (!isObject(value)
    || !isUuid(value.id)
    || !isNonEmptyString(value.name)
    || !isAccountType(value.account_type)
    || typeof value.is_default !== 'boolean'
    || !isSafeInteger(value.opening_balance_paise)
    || !isDate(value.opening_balance_as_of)
    || !isSafeInteger(value.balance_paise)
    || !isSafeInteger(value.goal_allocated_paise)
    || !isSafeInteger(value.available_to_spend_paise)
    || !isTimestamp(value.created_at)
    || !isTimestamp(value.updated_at)) {
    return invalid('account')
  }
  return {
    id: value.id,
    name: value.name,
    account_type: value.account_type,
    is_default: value.is_default,
    opening_balance_paise: value.opening_balance_paise,
    opening_balance_as_of: value.opening_balance_as_of,
    balance_paise: value.balance_paise,
    goal_allocated_paise: value.goal_allocated_paise,
    available_to_spend_paise: value.available_to_spend_paise,
    created_at: value.created_at,
    updated_at: value.updated_at,
  }
}

export function parseAccountListDto(value: unknown): AccountDto[] {
  if (!Array.isArray(value)) return invalid('account list')
  return value.map(parseAccountDto)
}

export function parseAccountBalanceDto(value: unknown): AccountBalanceDto {
  if (!isObject(value)
    || !isUuid(value.account_id)
    || !isSafeInteger(value.balance_paise)
    || !isSafeInteger(value.goal_allocated_paise)
    || !isSafeInteger(value.available_to_spend_paise)
    || !isDate(value.as_of)) {
    return invalid('account balance')
  }
  return {
    account_id: value.account_id,
    balance_paise: value.balance_paise,
    goal_allocated_paise: value.goal_allocated_paise,
    available_to_spend_paise: value.available_to_spend_paise,
    as_of: value.as_of,
  }
}

export function parseCategoryDto(value: unknown): CategoryDto {
  if (!isObject(value)
    || !isUuid(value.id)
    || !isNonEmptyString(value.name)
    || !isCategoryTransactionType(value.transaction_type)) {
    return invalid('category')
  }
  return {
    id: value.id,
    name: value.name,
    transaction_type: value.transaction_type,
  }
}

export function parseCategoryListDto(value: unknown): CategoryDto[] {
  if (!Array.isArray(value)) return invalid('category list')
  return value.map(parseCategoryDto)
}

export function parseTransactionDto(value: unknown): TransactionDto {
  if (!isObject(value)
    || !isUuid(value.id)
    || !isUuid(value.account_id)
    || !(value.category_id === null || isUuid(value.category_id))
    || !(value.category_name === null || isNonEmptyString(value.category_name))
    || !isCategoryTransactionType(value.transaction_type)
    || !isSafeInteger(value.amount_paise)
    || value.amount_paise <= 0
    || !isNonEmptyString(value.description)
    || value.description.length > 120
    || !isDate(value.transaction_date)
    || !(value.notes === null || typeof value.notes === 'string')
    || (typeof value.notes === 'string' && value.notes.length > 4000)
    || !isTimestamp(value.created_at)
    || !isTimestamp(value.updated_at)) {
    return invalid('transaction')
  }
  return {
    id: value.id,
    account_id: value.account_id,
    category_id: value.category_id,
    category_name: value.category_name,
    transaction_type: value.transaction_type,
    amount_paise: value.amount_paise,
    description: value.description,
    transaction_date: value.transaction_date,
    notes: value.notes,
    created_at: value.created_at,
    updated_at: value.updated_at,
  }
}

export function parseTransactionListDto(value: unknown): TransactionListDto {
  if (!isObject(value)
    || !Array.isArray(value.items)
    || !isSafeInteger(value.total)
    || value.total < 0
    || !isSafeInteger(value.offset)
    || value.offset < 0
    || !isSafeInteger(value.limit)
    || value.limit < 1
    || value.limit > 100
    || value.items.length > value.limit) {
    return invalid('transaction list')
  }
  return {
    items: value.items.map(parseTransactionDto),
    total: value.total,
    offset: value.offset,
    limit: value.limit,
  }
}

function isIntegerString(value: unknown): value is string {
  return typeof value === 'string' && /^-?(?:0|[1-9]\d*)$/.test(value)
}

export function parseBudgetDto(value: unknown): BudgetDto {
  if (!isObject(value)
    || !isUuid(value.id)
    || !isDate(value.month_start) || !value.month_start.endsWith('-01')
    || !(value.category_id === null || isUuid(value.category_id))
    || !(value.category_name === null || isNonEmptyString(value.category_name))
    || !isSafeInteger(value.limit_paise) || value.limit_paise <= 0
    || !isIntegerString(value.actual_spending_paise) || BigInt(value.actual_spending_paise) < 0n
    || !isIntegerString(value.remaining_paise)
    || !isIntegerString(value.percent_used_basis_points) || BigInt(value.percent_used_basis_points) < 0n
    || !isTimestamp(value.created_at) || !isTimestamp(value.updated_at)) {
    return invalid('budget')
  }
  return {
    id: value.id, month_start: value.month_start, category_id: value.category_id,
    category_name: value.category_name, limit_paise: value.limit_paise,
    actual_spending_paise: value.actual_spending_paise, remaining_paise: value.remaining_paise,
    percent_used_basis_points: value.percent_used_basis_points,
    created_at: value.created_at, updated_at: value.updated_at,
  }
}

export function parseBudgetListDto(value: unknown): BudgetDto[] {
  if (!Array.isArray(value)) return invalid('budget list')
  return value.map(parseBudgetDto)
}

export function parseGoalDto(value: unknown): GoalDto {
  if (!isObject(value)
    || !isUuid(value.id)
    || !isNonEmptyString(value.name) || value.name.length > 100
    || !(value.description === null || typeof value.description === 'string')
    || (typeof value.description === 'string' && value.description.length > 2000)
    || !isSafeInteger(value.target_paise) || value.target_paise <= 0
    || !(value.target_date === null || isDate(value.target_date))
    || !isSafeInteger(value.allocated_paise) || value.allocated_paise < 0
    || !isSafeInteger(value.remaining_target_paise)
    || !Array.isArray(value.account_allocations)
    || !value.account_allocations.every((item) => isObject(item) && isUuid(item.account_id) && isSafeInteger(item.allocated_paise) && item.allocated_paise >= 0)
    || !isTimestamp(value.created_at) || !isTimestamp(value.updated_at)) {
    return invalid('savings goal')
  }
  return {
    id: value.id, name: value.name, description: value.description,
    target_paise: value.target_paise, target_date: value.target_date,
    allocated_paise: value.allocated_paise, remaining_target_paise: value.remaining_target_paise,
    account_allocations: value.account_allocations.map((item) => ({ account_id: item.account_id as string, allocated_paise: item.allocated_paise as number })),
    created_at: value.created_at, updated_at: value.updated_at,
  }
}

function parsePage<T>(value: unknown, contract: string, parseItem: (item: unknown) => T): { items: T[]; total: number; offset: number; limit: number } {
  if (!isObject(value) || !Array.isArray(value.items) || !isSafeInteger(value.total) || value.total < 0
    || !isSafeInteger(value.offset) || value.offset < 0 || !isSafeInteger(value.limit) || value.limit < 1 || value.limit > 100
    || value.items.length > value.limit) return invalid(contract)
  return { items: value.items.map(parseItem), total: value.total, offset: value.offset, limit: value.limit }
}

export function parseGoalListDto(value: unknown): GoalListDto {
  return parsePage(value, 'savings goal list', parseGoalDto)
}

export function parseGoalEntryDto(value: unknown): GoalEntryDto {
  if (!isObject(value) || !isUuid(value.id) || !isUuid(value.goal_id) || !isUuid(value.account_id)
    || (value.entry_type !== 'contribution' && value.entry_type !== 'withdrawal')
    || !isSafeInteger(value.amount_paise) || value.amount_paise <= 0
    || !isDate(value.effective_date) || !isTimestamp(value.created_at)) return invalid('goal ledger entry')
  return { id: value.id, goal_id: value.goal_id, account_id: value.account_id, entry_type: value.entry_type, amount_paise: value.amount_paise, effective_date: value.effective_date, created_at: value.created_at }
}

export function parseGoalEntryListDto(value: unknown): GoalEntryListDto {
  return parsePage(value, 'goal ledger', parseGoalEntryDto)
}

export function parseGoalAccountSummaryDto(value: unknown): GoalAccountSummaryDto {
  if (!isObject(value) || !isUuid(value.account_id)
    || !isSafeInteger(value.balance_paise)
    || !isSafeInteger(value.goal_allocated_paise) || value.goal_allocated_paise < 0
    || !isSafeInteger(value.available_to_spend_paise)) return invalid('goal account summary')
  return {
    account_id: value.account_id,
    balance_paise: value.balance_paise,
    goal_allocated_paise: value.goal_allocated_paise,
    available_to_spend_paise: value.available_to_spend_paise,
  }
}

export function parseGoalMoneyMutationDto(value: unknown): GoalMoneyMutationDto {
  if (!isObject(value)) return invalid('goal allocation')
  return { entry: parseGoalEntryDto(value.entry), goal: parseGoalDto(value.goal), account: parseGoalAccountSummaryDto(value.account) }
}

export function parseDashboardSummaryDto(value: unknown): DashboardSummaryDto {
  if (!isObject(value)
    || !isDate(value.financial_date)
    || !isDate(value.month_start)
    || !isDate(value.month_end_exclusive)
    || value.month_start !== `${value.financial_date.slice(0, 7)}-01`
    || !isObject(value.account_totals)
    || !isSafeInteger(value.account_totals.account_count)
    || value.account_totals.account_count < 0
    || !isDecimalIntegerString(value.account_totals.balance_paise, true)
    || !isDecimalIntegerString(value.account_totals.goal_allocated_paise)
    || !isDecimalIntegerString(value.account_totals.available_to_spend_paise, true)
    || !isObject(value.cash_flow)
    || !isDecimalIntegerString(value.cash_flow.income_paise)
    || !isDecimalIntegerString(value.cash_flow.expenses_paise)
    || !isDecimalIntegerString(value.cash_flow.net_paise, true)
    || BigInt(value.cash_flow.income_paise) - BigInt(value.cash_flow.expenses_paise) !== BigInt(value.cash_flow.net_paise)
    || !Array.isArray(value.budgets)
    || !Array.isArray(value.goals)
    || !isSafeInteger(value.goals_total)
    || value.goals_total < value.goals.length
    || !isObject(value.recent_transactions)
    || !Array.isArray(value.recent_transactions.items)
    || !isSafeInteger(value.recent_transactions.total)
    || !isSafeInteger(value.recent_transactions.offset)
    || !isSafeInteger(value.recent_transactions.limit)
    || value.recent_transactions.offset !== 0
    || value.recent_transactions.limit !== 4
    || value.recent_transactions.items.length > value.recent_transactions.limit) {
    return invalid('dashboard summary')
  }

  const budgets = value.budgets.map((item): DashboardSummaryDto['budgets'][number] => {
    if (!isObject(item)
      || !isUuid(item.id)
      || !isDate(item.month_start)
      || item.month_start !== value.month_start
      || !(item.category_id === null || isUuid(item.category_id))
      || !(item.category_name === null || isNonEmptyString(item.category_name))
      || !isSafeInteger(item.limit_paise)
      || item.limit_paise <= 0
      || !isDecimalIntegerString(item.actual_spending_paise)
      || !isDecimalIntegerString(item.remaining_paise, true)
      || !isDecimalIntegerString(item.percent_used_basis_points)) {
      return invalid('dashboard budget')
    }
    if (BigInt(item.limit_paise) - BigInt(item.actual_spending_paise) !== BigInt(item.remaining_paise)) {
      return invalid('dashboard budget arithmetic')
    }
    return {
      id: item.id,
      month_start: item.month_start,
      category_id: item.category_id,
      category_name: item.category_name,
      limit_paise: item.limit_paise,
      actual_spending_paise: item.actual_spending_paise,
      remaining_paise: item.remaining_paise,
      percent_used_basis_points: item.percent_used_basis_points,
    }
  })

  const goals = value.goals.map((item): DashboardSummaryDto['goals'][number] => {
    if (!isObject(item)
      || !isUuid(item.id)
      || !isNonEmptyString(item.name)
      || !(item.target_date === null || isDate(item.target_date))
      || !isSafeInteger(item.target_paise)
      || item.target_paise <= 0
      || !isSafeInteger(item.allocated_paise)
      || item.allocated_paise < 0
      || !isSafeInteger(item.remaining_target_paise)
      || item.remaining_target_paise !== item.target_paise - item.allocated_paise) {
      return invalid('dashboard goal')
    }
    return {
      id: item.id,
      name: item.name,
      target_date: item.target_date,
      target_paise: item.target_paise,
      allocated_paise: item.allocated_paise,
      remaining_target_paise: item.remaining_target_paise,
    }
  })

  const items = value.recent_transactions.items.map((item): DashboardSummaryDto['recent_transactions']['items'][number] => {
    if (!isObject(item)
      || !isUuid(item.id)
      || !isUuid(item.account_id)
      || !(item.category_id === null || isUuid(item.category_id))
      || !(item.category_name === null || isNonEmptyString(item.category_name))
      || !isCategoryTransactionType(item.transaction_type)
      || !isSafeInteger(item.amount_paise)
      || item.amount_paise <= 0
      || !isNonEmptyString(item.description)
      || !isDate(item.transaction_date)) {
      return invalid('dashboard transaction')
    }
    return {
      id: item.id,
      account_id: item.account_id,
      category_id: item.category_id,
      category_name: item.category_name,
      transaction_type: item.transaction_type,
      amount_paise: item.amount_paise,
      description: item.description,
      transaction_date: item.transaction_date,
    }
  })

  if (value.recent_transactions.total < items.length) return invalid('dashboard transaction pagination')
  const expectedEnd = value.month_start.slice(0, 4) === '9999'
    ? null
    : (() => {
      const [year, month] = value.month_start.slice(0, 7).split('-').map(Number)
      return month === 12 ? `${year + 1}-01-01` : `${year}-${String(month + 1).padStart(2, '0')}-01`
    })()
  if (expectedEnd && value.month_end_exclusive !== expectedEnd) return invalid('dashboard month range')

  return {
    financial_date: value.financial_date,
    month_start: value.month_start,
    month_end_exclusive: value.month_end_exclusive,
    account_totals: {
      account_count: value.account_totals.account_count,
      balance_paise: value.account_totals.balance_paise,
      goal_allocated_paise: value.account_totals.goal_allocated_paise,
      available_to_spend_paise: value.account_totals.available_to_spend_paise,
    },
    cash_flow: {
      income_paise: value.cash_flow.income_paise,
      expenses_paise: value.cash_flow.expenses_paise,
      net_paise: value.cash_flow.net_paise,
    },
    budgets,
    goals,
    goals_total: value.goals_total,
    recent_transactions: {
      items,
      total: value.recent_transactions.total,
      offset: value.recent_transactions.offset,
      limit: value.recent_transactions.limit,
    },
  }
}
