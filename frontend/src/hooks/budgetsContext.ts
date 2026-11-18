import { createContext, useContext } from 'react'
import type { BudgetCreateInput, BudgetDto, BudgetUpdateInput } from '@/types/api'

export interface BudgetState { status: 'loading' | 'success' | 'error'; data: BudgetDto[]; error: string | null }
export interface BudgetsContextValue {
  monthStart: string
  state: BudgetState
  mutationError: string | null
  mutationRevision: number
  setMonthStart: (month: string) => void
  retry: () => Promise<void>
  create: (input: BudgetCreateInput) => Promise<void>
  update: (id: string, input: BudgetUpdateInput) => Promise<void>
  remove: (id: string) => Promise<void>
  isMutating: boolean
}
export const BudgetsContext = createContext<BudgetsContextValue | null>(null)
export function useBudgets(): BudgetsContextValue {
  const value = useContext(BudgetsContext)
  if (!value) throw new Error('useBudgets must be used inside BudgetsProvider.')
  return value
}
