import { useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from 'react'
import type { AssistantService } from '@/services/assistantService'
import type { FinanceRepository } from '@/services/financeRepository'
import type { UserPreferences } from '@/types/preferences'
import { FinanceContext, type FinanceContextValue } from './financeContext'

const defaultPreferences: UserPreferences = {
  currency: 'INR',
  theme: 'light',
  budgetAlerts: true,
  weeklySummary: false,
}

function readPreferences(): UserPreferences {
  if (typeof localStorage === 'undefined') return defaultPreferences
  try {
    const saved = localStorage.getItem('vibewealth-preferences')
    if (!saved) return defaultPreferences
    const parsed: Partial<UserPreferences> = JSON.parse(saved)
    return {
      currency: 'INR',
      theme: parsed.theme === 'dark' ? 'dark' : 'light',
      budgetAlerts: typeof parsed.budgetAlerts === 'boolean' ? parsed.budgetAlerts : defaultPreferences.budgetAlerts,
      weeklySummary: typeof parsed.weeklySummary === 'boolean' ? parsed.weeklySummary : defaultPreferences.weeklySummary,
    }
  } catch {
    return defaultPreferences
  }
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

interface FinanceProviderProps {
  children: ReactNode
  repository: FinanceRepository
  assistantService: AssistantService
}

export function FinanceProvider({ children, repository, assistantService }: FinanceProviderProps) {
  const snapshot = useSyncExternalStore(repository.subscribe, repository.getSnapshot, repository.getSnapshot)
  const [preferences, setPreferences] = useState(readPreferences)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [mutationError, setMutationError] = useState<string | null>(null)

  const retryLoad = useCallback(async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      await repository.load()
    } catch (error) {
      setLoadError(errorMessage(error))
    } finally {
      setIsLoading(false)
    }
  }, [repository])

  useEffect(() => {
    let active = true
    void repository.load().then(() => {
      if (active) setLoadError(null)
    }).catch((error: unknown) => {
      if (active) setLoadError(errorMessage(error))
    }).finally(() => {
      if (active) setIsLoading(false)
    })
    return () => { active = false }
  }, [repository])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', preferences.theme === 'dark')
    try {
      localStorage.setItem('vibewealth-preferences', JSON.stringify(preferences))
    } catch {
      // Preferences remain usable for this session when browser storage is unavailable.
    }
  }, [preferences])

  const runMutation = useCallback(async (operation: () => Promise<void>) => {
    setPendingCount((count) => count + 1)
    setMutationError(null)
    try {
      await operation()
    } catch (error) {
      setMutationError(errorMessage(error))
      throw error
    } finally {
      setPendingCount((count) => Math.max(0, count - 1))
    }
  }, [])

  const value = useMemo<FinanceContextValue>(() => ({
    snapshot,
    preferences,
    isLoading,
    loadError,
    retryLoad,
    isMutating: pendingCount > 0,
    mutationError,
    clearMutationError: () => setMutationError(null),
    requestAssistantReply: (question) => assistantService.reply(question),
    updatePreferences: (changes) => setPreferences((current) => ({ ...current, ...changes, currency: 'INR' })),
    addTransaction: (draft) => runMutation(() => repository.addTransaction(draft)),
    updateTransaction: (id, draft) => runMutation(() => repository.updateTransaction(id, draft)),
    deleteTransaction: (id) => runMutation(() => repository.deleteTransaction(id)),
    addBudget: (draft) => runMutation(() => repository.addBudget(draft)),
    updateBudget: (id, draft) => runMutation(() => repository.updateBudget(id, draft)),
    deleteBudget: (id) => runMutation(() => repository.deleteBudget(id)),
    addGoal: (draft) => runMutation(() => repository.addGoal(draft)),
    updateGoal: (id, draft) => runMutation(() => repository.updateGoal(id, draft)),
    deleteGoal: (id) => runMutation(() => repository.deleteGoal(id)),
    moveGoalMoney: (id, amount, direction) => runMutation(() => repository.moveGoalMoney(id, amount, direction)),
    updateProfile: (profile) => runMutation(() => repository.updateProfile(profile)),
  }), [assistantService, isLoading, loadError, mutationError, pendingCount, preferences, repository, retryLoad, runMutation, snapshot])

  return <FinanceContext.Provider value={value}>{children}</FinanceContext.Provider>
}
