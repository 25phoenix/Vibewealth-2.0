import { createContext, useContext } from 'react'
import type { DashboardSummaryDto } from '@/types/api'

export type DashboardSummaryState = {
  status: 'loading' | 'success' | 'error'
  data: DashboardSummaryDto | null
  error: string | null
}

export interface DashboardContextValue {
  summary: DashboardSummaryState
  retry: () => Promise<void>
}

export const DashboardContext = createContext<DashboardContextValue | null>(null)

export function useDashboard(): DashboardContextValue {
  const value = useContext(DashboardContext)
  if (!value) throw new Error('useDashboard must be used inside DashboardProvider.')
  return value
}
