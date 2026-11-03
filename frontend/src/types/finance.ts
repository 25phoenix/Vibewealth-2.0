export type TransactionType = 'income' | 'expense'

export interface Transaction {
  id: string
  merchant: string
  category: string
  date: string
  amount: number
  type: TransactionType
  initials: string
  color: string
}

export interface SpendingCategory {
  name: string
  amount: number
  share: number
  color: string
}

export interface FinanceSummary {
  balance: number
  income: number
  expenses: number
  savings: number
}
