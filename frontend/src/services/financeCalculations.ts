import type {
  BudgetProgress,
  CategorySpending,
  FinanceSnapshot,
  GoalProgress,
  MonthlySummary,
  Transaction,
} from '@/types/finance'
import { getTodayDateKey } from '@/lib/format'

export type TransactionTypeFilter = 'all' | 'income' | 'expense'
export type TransactionSort = 'date-desc' | 'date-asc' | 'amount-desc' | 'amount-asc'

export interface TransactionFilters {
  search: string
  type: TransactionTypeFilter
  category: string
  from: string
  to: string
  sortBy: TransactionSort
}

function isCompleted(transaction: Transaction, today: string) {
  return transaction.date <= today
}

function inMonth(date: string, month: string) {
  return date.startsWith(month)
}

export function summarizeTransactions(transactions: Transaction[], from?: string, to?: string, today = getTodayDateKey()) {
  return transactions.reduce((summary, transaction) => {
    if (!isCompleted(transaction, today)) return summary
    if ((from && transaction.date < from) || (to && transaction.date > to)) return summary
    if (transaction.type === 'income') summary.incomePaise += transaction.amountPaise
    else summary.expensesPaise += transaction.amountPaise
    summary.netPaise = summary.incomePaise - summary.expensesPaise
    return summary
  }, { incomePaise: 0, expensesPaise: 0, netPaise: 0 })
}

export function filterTransactions(transactions: Transaction[], filters: TransactionFilters) {
  const query = filters.search.trim().toLocaleLowerCase()
  const today = getTodayDateKey()
  return transactions
    .filter((transaction) => {
      if (!isCompleted(transaction, today)) return false
      const matchesText = !query || `${transaction.description} ${transaction.category} ${transaction.notes ?? ''}`.toLocaleLowerCase().includes(query)
      const matchesType = filters.type === 'all' || transaction.type === filters.type
      const matchesCategory = filters.category === 'all' || transaction.category === filters.category
      return matchesText && matchesType && matchesCategory && (!filters.from || transaction.date >= filters.from) && (!filters.to || transaction.date <= filters.to)
    })
    .sort((left, right) => {
      if (filters.sortBy === 'date-asc') return left.date.localeCompare(right.date)
      if (filters.sortBy === 'amount-desc') return right.amountPaise - left.amountPaise
      if (filters.sortBy === 'amount-asc') return left.amountPaise - right.amountPaise
      return right.date.localeCompare(left.date)
    })
}

export function getMonthlySummary(snapshot: FinanceSnapshot, month: string, today = getTodayDateKey()): MonthlySummary {
  const monthly = summarizeTransactions(snapshot.transactions, `${month}-01`, `${month}-31`, today)
  const balanceChanges = snapshot.transactions.reduce((total, transaction) => {
    if (transaction.date > today) return total
    return total + (transaction.type === 'income' ? transaction.amountPaise : -transaction.amountPaise)
  }, 0)

  return {
    balancePaise: snapshot.openingBalancePaise + balanceChanges,
    incomePaise: monthly.incomePaise,
    expensesPaise: monthly.expensesPaise,
    netPaise: monthly.netPaise,
  }
}

export function getCategorySpending(transactions: Transaction[], month: string, today = getTodayDateKey()): CategorySpending[] {
  const totals = new Map<string, number>()
  for (const transaction of transactions) {
    if (transaction.type !== 'expense' || !inMonth(transaction.date, month) || !isCompleted(transaction, today)) continue
    totals.set(transaction.category, (totals.get(transaction.category) ?? 0) + transaction.amountPaise)
  }

  const totalPaise = [...totals.values()].reduce((sum, amount) => sum + amount, 0)
  return [...totals.entries()]
    .map(([category, amountPaise]) => ({
      category,
      amountPaise,
      sharePercent: totalPaise === 0 ? 0 : Math.round((amountPaise * 100) / totalPaise),
    }))
    .sort((left, right) => right.amountPaise - left.amountPaise)
}

export function getRecentTransactions(transactions: Transaction[], month: string, limit = 5, today = getTodayDateKey()) {
  return transactions
    .filter((transaction) => inMonth(transaction.date, month) && isCompleted(transaction, today))
    .slice()
    .sort((left, right) => right.date.localeCompare(left.date) || right.id.localeCompare(left.id))
    .slice(0, limit)
}

export function getBudgetProgress(snapshot: FinanceSnapshot, month: string, today = getTodayDateKey()): BudgetProgress[] {
  return snapshot.budgets.filter((budget) => budget.month === month).map((budget) => {
    const spentPaise = snapshot.transactions
      .filter((transaction) => transaction.type === 'expense'
        && transaction.category === budget.category
        && inMonth(transaction.date, month)
        && isCompleted(transaction, today))
      .reduce((total, transaction) => total + transaction.amountPaise, 0)
    const usedPercent = budget.limitPaise === 0 ? 0 : Math.round((spentPaise * 100) / budget.limitPaise)

    return {
      ...budget,
      spentPaise,
      remainingPaise: budget.limitPaise - spentPaise,
      usedPercent,
      status: usedPercent > 100 ? 'exceeded' : usedPercent >= 80 ? 'approaching' : 'healthy',
    }
  })
}

export function getGoalProgress(snapshot: FinanceSnapshot): GoalProgress[] {
  return snapshot.goals.map((goal) => ({
    ...goal,
    remainingPaise: Math.max(0, goal.targetPaise - goal.savedPaise),
    progressPercent: goal.targetPaise === 0 ? 0 : Math.min(100, Math.round((goal.savedPaise * 100) / goal.targetPaise)),
  }))
}

export function getBudgetOverview(snapshot: FinanceSnapshot, budgets: BudgetProgress[], month: string, today = getTodayDateKey()) {
  const allocatedPaise = budgets.reduce((sum, budget) => sum + budget.limitPaise, 0)
  const categorySpending = getCategorySpending(snapshot.transactions, month, today)
  const budgetedCategories = new Set(budgets.map((budget) => budget.category))
  const budgetedCategorySpendingPaise = categorySpending
    .filter((item) => budgetedCategories.has(item.category))
    .reduce((sum, item) => sum + item.amountPaise, 0)
  const totalActualSpendingPaise = categorySpending.reduce((sum, item) => sum + item.amountPaise, 0)
  const unbudgetedCategorySpendingPaise = totalActualSpendingPaise - budgetedCategorySpendingPaise
  return {
    allocatedPaise,
    budgetedCategorySpendingPaise,
    unbudgetedCategorySpendingPaise,
    totalActualSpendingPaise,
    remainingPaise: allocatedPaise - budgetedCategorySpendingPaise,
    utilizationPercent: allocatedPaise === 0 ? 0 : Math.round((budgetedCategorySpendingPaise * 100) / allocatedPaise),
    categoriesToWatch: budgets.filter((budget) => budget.status !== 'healthy').length,
  }
}

export function getGoalOverview(goals: GoalProgress[]) {
  const savedPaise = goals.reduce((sum, goal) => sum + goal.savedPaise, 0)
  const targetPaise = goals.reduce((sum, goal) => sum + goal.targetPaise, 0)
  return {
    savedPaise,
    targetPaise,
    remainingPaise: Math.max(0, targetPaise - savedPaise),
    progressPercent: targetPaise === 0 ? 0 : Math.min(100, Math.round((savedPaise * 100) / targetPaise)),
  }
}

