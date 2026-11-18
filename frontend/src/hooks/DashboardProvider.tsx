import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, ApiNetworkError } from '@/services/api/apiClient'
import { dashboardApi } from '@/services/api/dashboardApi'
import type { DashboardSummaryDto } from '@/types/api'
import { useTransactions } from './transactionsContext'
import { useBudgets } from './budgetsContext'
import { useSavingsGoals } from './savingsGoalsContext'
import { DashboardContext, type DashboardContextValue, type DashboardSummaryState } from './dashboardContext'

interface DashboardService {
  summary(): Promise<DashboardSummaryDto>
}

interface DashboardProviderProps {
  children: ReactNode
  sessionGeneration: number
  onUnauthorized: () => Promise<void>
  service?: DashboardService
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError || error instanceof ApiNetworkError) return error.message
  return 'Could not load your financial summary. Please try again.'
}

function DashboardSession({ children, onUnauthorized, service = dashboardApi }: Omit<DashboardProviderProps, 'sessionGeneration'>) {
  const { mutationRevision: transactionRevision } = useTransactions()
  const { mutationRevision: budgetRevision } = useBudgets()
  const { mutationRevision: goalRevision } = useSavingsGoals()
  const [summary, setSummary] = useState<DashboardSummaryState>({ status: 'loading', data: null, error: null })
  const active = useRef(false)
  const generation = useRef(0)
  const inFlight = useRef<Promise<DashboardSummaryDto> | null>(null)
  const previousRevision = useRef<string | null>(null)
  const revisionKey = `${transactionRevision}:${budgetRevision}:${goalRevision}`

  const load = useCallback(async (force = false) => {
    const request = !force && inFlight.current
      ? inFlight.current
      : Promise.resolve().then(() => service.summary())
    const requestGeneration = ++generation.current
    inFlight.current = request
    try {
      const data = await request
      if (active.current && generation.current === requestGeneration) {
        setSummary({ status: 'success', data, error: null })
      }
    } catch (error) {
      if (active.current && generation.current === requestGeneration) {
        setSummary({ status: 'error', data: null, error: errorMessage(error) })
        if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
      }
    } finally {
      if (inFlight.current === request) inFlight.current = null
    }
  }, [onUnauthorized, service])

  useEffect(() => {
    active.current = true
    const shouldRefresh = previousRevision.current !== null && previousRevision.current !== revisionKey
    previousRevision.current = revisionKey
    if (shouldRefresh) setSummary({ status: 'loading', data: null, error: null })
    void load(shouldRefresh)
    return () => {
      active.current = false
      generation.current += 1
    }
  }, [load, revisionKey])

  const retry = useCallback(() => {
    setSummary({ status: 'loading', data: null, error: null })
    return load(true)
  }, [load])

  const value = useMemo<DashboardContextValue>(() => ({ summary, retry }), [summary, retry])
  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>
}

export function DashboardProvider(props: DashboardProviderProps) {
  return <DashboardSession key={props.sessionGeneration} onUnauthorized={props.onUnauthorized} service={props.service}>{props.children}</DashboardSession>
}
