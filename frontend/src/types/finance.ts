export type MoneyPaise = number
export type TransactionType = 'income' | 'expense'

export interface Transaction {
  id: string
  description: string
  amountPaise: MoneyPaise
  type: TransactionType
  category: string
  date: string
  notes?: string
}

export type TransactionDraft = Omit<Transaction, 'id'>

export interface Budget {
  id: string
  category: string
  limitPaise: MoneyPaise
  month: string
}

export type BudgetDraft = Omit<Budget, 'id'>

export interface SavingsGoal {
  id: string
  name: string
  targetPaise: MoneyPaise
  savedPaise: MoneyPaise
  targetDate: string
}

export type SavingsGoalDraft = Omit<SavingsGoal, 'id' | 'savedPaise'>

export interface UserProfile {
  name: string
  email: string
  occupation: string
}

export interface FinanceSnapshot {
  openingBalancePaise: MoneyPaise
  transactions: Transaction[]
  budgets: Budget[]
  goals: SavingsGoal[]
  profile: UserProfile
  categories: CategoryOption[]
}

export interface CategoryOption {
  name: string
  type: TransactionType | 'both'
}

export interface CategorySpending {
  category: string
  amountPaise: MoneyPaise
  sharePercent: number
}

export interface MonthlySummary {
  balancePaise: MoneyPaise
  incomePaise: MoneyPaise
  expensesPaise: MoneyPaise
  netPaise: MoneyPaise
}

export interface BudgetProgress extends Budget {
  spentPaise: MoneyPaise
  remainingPaise: MoneyPaise
  usedPercent: number
  status: 'healthy' | 'approaching' | 'exceeded'
}

export interface GoalProgress extends SavingsGoal {
  remainingPaise: MoneyPaise
  progressPercent: number
}
