import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, ApiNetworkError } from '@/services/api/apiClient'
import { budgetsApi } from '@/services/api/budgetsApi'
import type { BudgetCreateInput, BudgetDto, BudgetUpdateInput } from '@/types/api'
import { getIndiaMonthStart, getMonthStartDateKey } from '@/lib/format'
import { BudgetsContext, type BudgetState, type BudgetsContextValue } from './budgetsContext'

interface BudgetService {
  list(monthStart?: string): Promise<BudgetDto[]>
  create(input: BudgetCreateInput): Promise<BudgetDto>
  update(id: string, input: BudgetUpdateInput): Promise<BudgetDto>
  delete(id: string): Promise<void>
}
interface Props { children: ReactNode; sessionGeneration: number; onUnauthorized: () => Promise<void>; service?: BudgetService }
function message(error: unknown) { return error instanceof ApiError || error instanceof ApiNetworkError ? error.message : 'Could not load budgets. Please try again.' }
function BudgetSession({ children, onUnauthorized, service = budgetsApi }: Omit<Props, 'sessionGeneration'>) {
  const [monthStart, setMonthStart] = useState(() => getIndiaMonthStart())
  const [state, setState] = useState<BudgetState>({ status: 'loading', data: [], error: null })
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [isMutating, setIsMutating] = useState(false)
  const [mutationRevision, setMutationRevision] = useState(0)
  const [reload, setReload] = useState(0)
  const active = useRef(false)
  const generation = useRef(0)
  const inFlight = useRef<{ key: string; promise: Promise<BudgetDto[]>; generation: number } | null>(null)
  const mutationLock = useRef(false)

  const load = useCallback(async (month: string, force = false) => {
    const key = month
    if (!force && inFlight.current?.key === key) {
      const requestGeneration = generation.current
      return inFlight.current.promise.then(
        (data) => { if (active.current && generation.current === requestGeneration && monthStart === month) setState({ status: 'success', data, error: null }) },
        (error) => {
          if (active.current && generation.current === requestGeneration && monthStart === month) {
            setState({ status: 'error', data: [], error: message(error) })
            if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
          }
        },
      )
    }
    const requestGeneration = ++generation.current
    const request = Promise.resolve().then(() => service.list(month))
    inFlight.current = { key, promise: request, generation: requestGeneration }
    try {
      const data = await request
      if (active.current && generation.current === requestGeneration) setState({ status: 'success', data, error: null })
    } catch (error) {
      if (active.current && generation.current === requestGeneration) {
        setState({ status: 'error', data: [], error: message(error) })
        if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
      }
    } finally { if (inFlight.current?.generation === requestGeneration) inFlight.current = null }
  }, [monthStart, onUnauthorized, service])

  const invalidateAndReload = useCallback(() => {
    generation.current += 1
    inFlight.current = null
    setState({ status: 'loading', data: [], error: null })
    setReload((value) => value + 1)
  }, [])
  useEffect(() => {
    active.current = true
    void load(monthStart)
    return () => { active.current = false; generation.current += 1 }
  }, [load, monthStart, reload])
  const changeMonth = useCallback((month: string) => {
    const normalizedMonthStart = /^\d{4}-\d{2}$/.test(month) ? getMonthStartDateKey(month) : getMonthStartDateKey(month.slice(0, 7))
    setState({ status: 'loading', data: [], error: null })
    setMonthStart(normalizedMonthStart)
  }, [])
  const retry = useCallback(() => { setState({ status: 'loading', data: [], error: null }); return load(monthStart, true) }, [load, monthStart])
  const mutate = useCallback(async (operation: () => Promise<unknown>) => {
    if (mutationLock.current) throw new Error('A budget change is already being saved.')
    mutationLock.current = true; setIsMutating(true); setMutationError(null)
    try { await operation(); setMutationRevision((value) => value + 1); invalidateAndReload() }
    catch (error) {
      const text = message(error); setMutationError(text)
      if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
      throw new Error(text)
    } finally { mutationLock.current = false; setIsMutating(false) }
  }, [invalidateAndReload, onUnauthorized])
  const create = useCallback((input: BudgetCreateInput) => mutate(() => service.create(input)), [mutate, service])
  const update = useCallback((id: string, input: BudgetUpdateInput) => mutate(() => service.update(id, input)), [mutate, service])
  const remove = useCallback((id: string) => mutate(() => service.delete(id)), [mutate, service])
  const value = useMemo<BudgetsContextValue>(() => ({ monthStart, state, mutationError, mutationRevision, setMonthStart: changeMonth, retry, create, update, remove, isMutating }), [monthStart, state, mutationError, mutationRevision, changeMonth, retry, create, update, remove, isMutating])
  return <BudgetsContext.Provider value={value}>{children}</BudgetsContext.Provider>
}
export function BudgetsProvider(props: Props) { return <BudgetSession key={props.sessionGeneration} onUnauthorized={props.onUnauthorized} service={props.service}>{props.children}</BudgetSession> }
