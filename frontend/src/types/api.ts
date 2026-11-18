export interface AuthUserDto {
  id: string
  email: string
  display_name: string | null
}

export interface CsrfTokenDto {
  csrf_token: string
}

export const API_ACCOUNT_TYPES = ['cash', 'bank', 'wallet'] as const
export type ApiAccountType = typeof API_ACCOUNT_TYPES[number]

export const API_CATEGORY_TRANSACTION_TYPES = ['income', 'expense'] as const
export type ApiCategoryTransactionType = typeof API_CATEGORY_TRANSACTION_TYPES[number]

export interface AccountDto {
  id: string
  name: string
  account_type: ApiAccountType
  is_default: boolean
  opening_balance_paise: number
  opening_balance_as_of: string
  balance_paise: number
  goal_allocated_paise: number
  available_to_spend_paise: number
  created_at: string
  updated_at: string
}

export interface AccountBalanceDto {
  account_id: string
  balance_paise: number
  goal_allocated_paise: number
  available_to_spend_paise: number
  as_of: string
}

export interface CategoryDto {
  id: string
  name: string
  transaction_type: ApiCategoryTransactionType
}

export type ApiTransactionType = ApiCategoryTransactionType

export interface TransactionDto {
  id: string
  account_id: string
  category_id: string | null
  category_name: string | null
  transaction_type: ApiTransactionType
  amount_paise: number
  description: string
  transaction_date: string
  notes: string | null
  created_at: string
  updated_at: string
}

export interface TransactionListDto {
  items: TransactionDto[]
  total: number
  offset: number
  limit: number
}

export interface TransactionCreateInput {
  account_id: string
  category_id: string
  transaction_type: ApiTransactionType
  amount_paise: number
  description: string
  transaction_date: string
  notes?: string
}

export interface TransactionListQuery {
  account_id?: string
  transaction_type?: ApiTransactionType
  category_id?: string
  date_from?: string
  date_to?: string
  offset: number
  limit: number
}

export interface BudgetDto {
  id: string
  month_start: string
  category_id: string | null
  category_name: string | null
  limit_paise: number
  actual_spending_paise: string
  remaining_paise: string
  percent_used_basis_points: string
  created_at: string
  updated_at: string
}

export interface BudgetCreateInput {
  month_start: string
  category_id: string | null
  limit_paise: number
}

export type BudgetUpdateInput = Partial<BudgetCreateInput>

export interface GoalDto {
  id: string
  name: string
  description: string | null
  target_paise: number
  target_date: string | null
  allocated_paise: number
  remaining_target_paise: number
  account_allocations: Array<{ account_id: string; allocated_paise: number }>
  created_at: string
  updated_at: string
}

export interface GoalListDto {
  items: GoalDto[]
  total: number
  offset: number
  limit: number
}

export interface GoalCreateInput {
  name: string
  description: string | null
  target_paise: number
  target_date: string | null
}

export type GoalUpdateInput = Partial<GoalCreateInput>

export interface GoalEntryDto {
  id: string
  goal_id: string
  account_id: string
  entry_type: 'contribution' | 'withdrawal'
  amount_paise: number
  effective_date: string
  created_at: string
}

export interface GoalEntryListDto {
  items: GoalEntryDto[]
  total: number
  offset: number
  limit: number
}

export interface GoalAccountSummaryDto {
  account_id: string
  balance_paise: number
  goal_allocated_paise: number
  available_to_spend_paise: number
}

export interface GoalMoneyMutationDto {
  entry: GoalEntryDto
  goal: GoalDto
  account: GoalAccountSummaryDto
}

export interface DashboardAccountTotalsDto {
  account_count: number
  balance_paise: string
  goal_allocated_paise: string
  available_to_spend_paise: string
}

export interface DashboardCashFlowDto {
  income_paise: string
  expenses_paise: string
  net_paise: string
}

export interface DashboardBudgetDto {
  id: string
  month_start: string
  category_id: string | null
  category_name: string | null
  limit_paise: number
  actual_spending_paise: string
  remaining_paise: string
  percent_used_basis_points: string
}

export interface DashboardGoalDto {
  id: string
  name: string
  target_date: string | null
  target_paise: number
  allocated_paise: number
  remaining_target_paise: number
}

export interface DashboardTransactionDto {
  id: string
  account_id: string
  category_id: string | null
  category_name: string | null
  transaction_type: ApiTransactionType
  amount_paise: number
  description: string
  transaction_date: string
}

export interface DashboardSummaryDto {
  financial_date: string
  month_start: string
  month_end_exclusive: string
  account_totals: DashboardAccountTotalsDto
  cash_flow: DashboardCashFlowDto
  budgets: DashboardBudgetDto[]
  goals: DashboardGoalDto[]
  goals_total: number
  recent_transactions: {
    items: DashboardTransactionDto[]
    total: number
    offset: number
    limit: number
  }
}
