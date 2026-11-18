import { createContext, useContext } from 'react'
import type { GoalCreateInput, GoalEntryListDto, GoalListDto, GoalUpdateInput } from '@/types/api'

export interface GoalsResource<T> { status: 'loading' | 'success' | 'error'; data: T | null; error: string | null }
export interface SavingsGoalsContextValue {
  goals: GoalsResource<GoalListDto>
  ledger: GoalsResource<GoalEntryListDto>
  selectedGoalId: string | null
  goalOffset: number
  ledgerOffset: number
  mutationError: string | null
  mutationRevision: number
  selectGoal: (id: string | null) => void
  setGoalOffset: (offset: number) => void
  setLedgerOffset: (offset: number) => void
  retryGoals: () => Promise<void>
  retryLedger: () => Promise<void>
  create: (input: GoalCreateInput) => Promise<void>
  update: (id: string, input: GoalUpdateInput) => Promise<void>
  remove: (id: string) => Promise<void>
  contribute: (id: string, accountId: string, amountPaise: number) => Promise<void>
  withdraw: (id: string, accountId: string, amountPaise: number) => Promise<void>
  isMutating: boolean
}
export const SavingsGoalsContext = createContext<SavingsGoalsContextValue | null>(null)
export function useSavingsGoals(): SavingsGoalsContextValue {
  const value = useContext(SavingsGoalsContext)
  if (!value) throw new Error('useSavingsGoals must be used inside SavingsGoalsProvider.')
  return value
}
