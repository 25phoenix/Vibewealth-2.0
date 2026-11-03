import type { FinanceSummary, SpendingCategory, Transaction } from '@/types/finance'

export const financeSummary: FinanceSummary = {
  balance: 248650,
  income: 68400,
  expenses: 42180,
  savings: 26220,
}

export const monthlyChanges = {
  balance: { change: '8.2%', direction: 'up' as const, favorable: true },
  income: { change: '12.5%', direction: 'up' as const, favorable: true },
  expenses: { change: '4.3%', direction: 'down' as const, favorable: true },
  savings: { change: '6.8%', direction: 'up' as const, favorable: true },
  label: 'vs last month',
}

export const spendingTotal = 42180

export const spendingCategories: SpendingCategory[] = [
  { name: 'Food & dining', amount: 12400, share: 29, color: 'var(--chart-1)' },
  { name: 'Transport', amount: 6800, share: 16, color: 'var(--chart-2)' },
  { name: 'Shopping', amount: 9200, share: 22, color: 'var(--chart-3)' },
  { name: 'Bills & utilities', amount: 7800, share: 18, color: 'var(--chart-4)' },
  { name: 'Other', amount: 5980, share: 15, color: 'var(--chart-5)' },
]

export const transactions: Transaction[] = [
  { id: 'txn-1', merchant: 'Blue Tokai Coffee', category: 'Food & dining', date: 'Today, 10:42 AM', amount: 420, type: 'expense', initials: 'BT', color: 'mint' },
  { id: 'txn-2', merchant: 'Monthly stipend', category: 'Income', date: 'Today, 9:15 AM', amount: 24000, type: 'income', initials: 'MS', color: 'blue' },
  { id: 'txn-3', merchant: 'Uber', category: 'Transport', date: 'Yesterday', amount: 286, type: 'expense', initials: 'U', color: 'slate' },
  { id: 'txn-4', merchant: 'Zepto', category: 'Groceries', date: 'Yesterday', amount: 1240, type: 'expense', initials: 'Z', color: 'yellow' },
]
