import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiContractError, ApiError, ApiNetworkError } from '@/services/api/apiClient'
import { GoalAllocationOutcomeUnknownError, goalsApi } from '@/services/api/goalsApi'
import type { GoalCreateInput, GoalDto, GoalEntryListDto, GoalListDto, GoalMoneyMutationDto, GoalUpdateInput } from '@/types/api'
import { useAccountCategoryData } from './accountCategoryContext'
import { SavingsGoalsContext, type GoalsResource, type SavingsGoalsContextValue } from './savingsGoalsContext'

interface GoalsService {
  list(offset?: number, limit?: number): Promise<GoalListDto>
  create(input: GoalCreateInput): Promise<GoalDto>
  update(id: string, input: GoalUpdateInput): Promise<GoalDto>
  delete(id: string): Promise<void>
  entries(id: string, offset?: number, limit?: number): Promise<GoalEntryListDto>
  contribute(id: string, accountId: string, amountPaise: number): Promise<GoalMoneyMutationDto>
  withdraw(id: string, accountId: string, amountPaise: number): Promise<GoalMoneyMutationDto>
}
interface Props { children: ReactNode; sessionGeneration: number; onUnauthorized: () => Promise<void>; service?: GoalsService }
function message(error: unknown, fallback = 'Could not load savings goals. Please try again.') {
  if (error instanceof GoalAllocationOutcomeUnknownError) return error.message
  if (error instanceof ApiContractError) {
    return `${error.message}${import.meta.env.DEV ? ' Check the backend response contract and ensure database migrations are up to date.' : ''}`
  }
  if (error instanceof ApiError) {
    if (error.status < 500) return error.message
    return `${error.message} (HTTP ${error.status})${import.meta.env.DEV ? ' Check backend logs and ensure database migrations are up to date.' : ''}`
  }
  if (error instanceof ApiNetworkError) return error.message
  return fallback
}
const PAGE_SIZE = 50

function GoalsSession({ children, onUnauthorized, service = goalsApi }: Omit<Props, 'sessionGeneration'>) {
  const { retryAccounts } = useAccountCategoryData()
  const [goals, setGoals] = useState<GoalsResource<GoalListDto>>({ status: 'loading', data: null, error: null })
  const [ledger, setLedger] = useState<GoalsResource<GoalEntryListDto>>({ status: 'loading', data: null, error: null })
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null)
  const [goalOffset, setGoalOffset] = useState(0)
  const [ledgerOffset, setLedgerOffset] = useState(0)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [mutationRevision, setMutationRevision] = useState(0)
  const [isMutating, setIsMutating] = useState(false)
  const [reload, setReload] = useState(0)
  const [ledgerReload, setLedgerReload] = useState(0)
  const active = useRef(false)
  const goalsGeneration = useRef(0)
  const ledgerGeneration = useRef(0)
  const goalsFlight = useRef<{ key: number; promise: Promise<GoalListDto>; generation: number } | null>(null)
  const ledgerFlight = useRef<{ key: string; promise: Promise<GoalEntryListDto>; generation: number } | null>(null)
  const mutationLock = useRef(false)

  const loadGoals = useCallback(async (force = false) => {
    if (!force && goalsFlight.current?.key === goalOffset) {
      const requestGeneration = goalsGeneration.current
      return goalsFlight.current.promise.then(
        (data) => { if (active.current && goalsGeneration.current === requestGeneration && data.offset === goalOffset) setGoals({ status: 'success', data, error: null }) },
        (error) => {
          if (active.current && goalsGeneration.current === requestGeneration) {
            setGoals({ status: 'error', data: null, error: message(error) })
            if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
          }
        },
      )
    }
    const requestGeneration = ++goalsGeneration.current
    const request = Promise.resolve().then(() => service.list(goalOffset, PAGE_SIZE))
    goalsFlight.current = { key: goalOffset, promise: request, generation: requestGeneration }
    try {
      const data = await request
      if (active.current && goalsGeneration.current === requestGeneration) {
        if (goalOffset > 0 && data.items.length === 0) { setGoalOffset(Math.max(0, Math.ceil(data.total / data.limit) - 1) * data.limit); return }
        setGoals({ status: 'success', data, error: null })
      }
    } catch (error) {
      if (active.current && goalsGeneration.current === requestGeneration) {
        setGoals({ status: 'error', data: null, error: message(error) })
        if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
      }
    } finally { if (goalsFlight.current?.generation === requestGeneration) goalsFlight.current = null }
  }, [goalOffset, onUnauthorized, service])

  const loadLedger = useCallback(async (goalId: string, force = false) => {
    const offset = ledgerOffset
    const key = `${goalId}:${offset}:${PAGE_SIZE}`
    if (!force && ledgerFlight.current?.key === key) {
      const requestGeneration = ledgerGeneration.current
      return ledgerFlight.current.promise.then(
        (data) => { if (active.current && ledgerGeneration.current === requestGeneration && selectedGoalId === goalId && data.offset === ledgerOffset) setLedger({ status: 'success', data, error: null }) },
        (error) => {
          if (active.current && ledgerGeneration.current === requestGeneration && selectedGoalId === goalId && ledgerOffset === offset) {
            setLedger({ status: 'error', data: null, error: message(error, 'Could not load goal history. Please try again.') })
            if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
          }
        },
      )
    }
    const requestGeneration = ++ledgerGeneration.current
    const request = Promise.resolve().then(() => service.entries(goalId, offset, PAGE_SIZE))
    ledgerFlight.current = { key, promise: request, generation: requestGeneration }
    try {
      const data = await request
      if (active.current && ledgerGeneration.current === requestGeneration && selectedGoalId === goalId && ledgerOffset === offset) {
        if (offset > 0 && data.items.length === 0) { setLedgerOffset(Math.max(0, Math.ceil(data.total / data.limit) - 1) * data.limit); return }
        setLedger({ status: 'success', data, error: null })
      }
    } catch (error) {
      if (active.current && ledgerGeneration.current === requestGeneration && selectedGoalId === goalId) {
        setLedger({ status: 'error', data: null, error: message(error, 'Could not load goal history. Please try again.') })
        if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
      }
    } finally { if (ledgerFlight.current?.generation === requestGeneration) ledgerFlight.current = null }
  }, [ledgerOffset, onUnauthorized, selectedGoalId, service])

  useEffect(() => {
    active.current = true
    void loadGoals()
    return () => { active.current = false; goalsGeneration.current += 1; ledgerGeneration.current += 1 }
  }, [loadGoals, reload])
  useEffect(() => {
    if (selectedGoalId) void loadLedger(selectedGoalId)
    else { ledgerGeneration.current += 1; ledgerFlight.current = null }
  }, [selectedGoalId, loadLedger, ledgerReload])

  const retryGoals = useCallback(() => { setGoals({ status: 'loading', data: null, error: null }); return loadGoals(true) }, [loadGoals])
  const retryLedger = useCallback(() => { if (!selectedGoalId) return Promise.resolve(); setLedger({ status: 'loading', data: null, error: null }); return loadLedger(selectedGoalId, true) }, [loadLedger, selectedGoalId])
  const refreshAfterMutation = useCallback((deletedGoalId?: string, refreshAccounts = false) => {
    goalsGeneration.current += 1; goalsFlight.current = null
    ledgerGeneration.current += 1; ledgerFlight.current = null
    setGoalOffset(0); setLedgerOffset(0)
    setGoals({ status: 'loading', data: null, error: null })
    if (selectedGoalId && selectedGoalId === deletedGoalId) {
      // The backend soft-deletes a goal and its ledger endpoint then returns 404.
      setSelectedGoalId(null)
      setLedger({ status: 'success', data: null, error: null })
    } else if (selectedGoalId) {
      setLedger({ status: 'loading', data: null, error: null })
      setLedgerReload((value) => value + 1)
    } else {
      setLedger({ status: 'success', data: null, error: null })
    }
    setReload((value) => value + 1)
    if (refreshAccounts) void Promise.resolve().then(retryAccounts).catch(() => {})
  }, [retryAccounts, selectedGoalId])
  const mutate = useCallback(async (operation: () => Promise<unknown>, deletedGoalId?: string, refreshAccounts = false, failureMessage = 'Could not save savings goal. Please try again.') => {
    if (mutationLock.current) throw new Error('A savings goal change is already being saved.')
    mutationLock.current = true; setIsMutating(true); setMutationError(null)
    try { await operation(); setMutationRevision((value) => value + 1); refreshAfterMutation(deletedGoalId, refreshAccounts) }
    catch (error) {
      const text = message(error, failureMessage); setMutationError(text)
      if (error instanceof ApiError && error.status === 401) void onUnauthorized().catch(() => {})
      if (error instanceof GoalAllocationOutcomeUnknownError) {
        refreshAfterMutation(undefined, true)
        throw error
      }
      throw new Error(text)
    } finally { mutationLock.current = false; setIsMutating(false) }
  }, [onUnauthorized, refreshAfterMutation])
  const create = useCallback((input: GoalCreateInput) => mutate(() => service.create(input)), [mutate, service])
  const update = useCallback((id: string, input: GoalUpdateInput) => mutate(() => service.update(id, input)), [mutate, service])
  const remove = useCallback((id: string) => mutate(() => service.delete(id), id, true, 'Could not delete savings goal. Please try again.'), [mutate, service])
  const contribute = useCallback((id: string, accountId: string, amountPaise: number) => mutate(() => service.contribute(id, accountId, amountPaise), undefined, true, 'Could not save goal allocation. Please try again.'), [mutate, service])
  const withdraw = useCallback((id: string, accountId: string, amountPaise: number) => mutate(() => service.withdraw(id, accountId, amountPaise), undefined, true, 'Could not withdraw from savings goal. Please try again.'), [mutate, service])
  const selectGoal = useCallback((id: string | null) => { setSelectedGoalId(id); setLedgerOffset(0); setLedger(id ? { status: 'loading', data: null, error: null } : { status: 'success', data: null, error: null }) }, [])
  const changeGoalOffset = useCallback((offset: number) => { setGoals({ status: 'loading', data: null, error: null }); setGoalOffset(offset) }, [])
  const changeLedgerOffset = useCallback((offset: number) => { setLedger({ status: 'loading', data: null, error: null }); setLedgerOffset(offset) }, [])
  const value = useMemo<SavingsGoalsContextValue>(() => ({ goals, ledger, selectedGoalId, goalOffset, ledgerOffset, mutationError, mutationRevision, selectGoal, setGoalOffset: changeGoalOffset, setLedgerOffset: changeLedgerOffset, retryGoals, retryLedger, create, update, remove, contribute, withdraw, isMutating }), [goals, ledger, selectedGoalId, goalOffset, ledgerOffset, mutationError, mutationRevision, selectGoal, changeGoalOffset, changeLedgerOffset, retryGoals, retryLedger, create, update, remove, contribute, withdraw, isMutating])
  return <SavingsGoalsContext.Provider value={value}>{children}</SavingsGoalsContext.Provider>
}
export function SavingsGoalsProvider(props: Props) { return <GoalsSession key={props.sessionGeneration} onUnauthorized={props.onUnauthorized} service={props.service}>{props.children}</GoalsSession> }
