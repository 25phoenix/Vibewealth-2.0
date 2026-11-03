import { createContext } from 'react'
import type { BudgetDraft, FinanceSnapshot, SavingsGoalDraft, TransactionDraft, UserProfile } from '@/types/finance'
import type { UserPreferences } from '@/types/preferences'

export interface FinanceContextValue {
  snapshot: FinanceSnapshot
  preferences: UserPreferences
  isLoading: boolean
  loadError: string | null
  retryLoad: () => Promise<void>
  isMutating: boolean
  mutationError: string | null
  clearMutationError: () => void
  requestAssistantReply: (question: string) => Promise<string>
  updatePreferences: (changes: Partial<UserPreferences>) => void
  addTransaction: (draft: TransactionDraft) => Promise<void>
  updateTransaction: (id: string, draft: TransactionDraft) => Promise<void>
  deleteTransaction: (id: string) => Promise<void>
  addBudget: (draft: BudgetDraft) => Promise<void>
  updateBudget: (id: string, draft: BudgetDraft) => Promise<void>
  deleteBudget: (id: string) => Promise<void>
  addGoal: (draft: SavingsGoalDraft) => Promise<void>
  updateGoal: (id: string, draft: SavingsGoalDraft) => Promise<void>
  deleteGoal: (id: string) => Promise<void>
  moveGoalMoney: (id: string, amountPaise: number, direction: 'add' | 'withdraw') => Promise<void>
  updateProfile: (profile: UserProfile) => Promise<void>
}

export const FinanceContext = createContext<FinanceContextValue | null>(null)
