import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, ApiNetworkError } from '@/services/api/apiClient'
import { AuthFinalizationError, authApi, type AuthApi } from '@/services/api/authApi'
import type { AuthUserDto } from '@/types/api'
import type { AuthSessionIdentity } from '@/types/auth'
import { AuthOperationGuard } from './authOperationGuard'
import { AuthContext, type AuthContextValue, type SessionStatus } from './authContext'

const RECONCILIATION_MESSAGE = 'The server accepted your request, but VibeWealth could not finish verifying the session. Retry to check the existing session; do not submit your credentials again.'

function errorMessage(error: unknown): string {
  if (error instanceof ApiNetworkError) return error.message
  if (error instanceof ApiError) return error.message
  return 'Something went wrong. Please try again.'
}

interface AuthProviderProps {
  children: ReactNode
  service?: AuthApi
}

export function AuthProvider({ children, service = authApi }: AuthProviderProps) {
  const [status, setStatus] = useState<SessionStatus>('restoring')
  const [user, setUser] = useState<AuthUserDto | null>(null)
  const [sessionIdentity, setSessionIdentity] = useState<AuthSessionIdentity | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const operationGuard = useRef(new AuthOperationGuard())
  const nextSessionGeneration = useRef(0)
  const submitLock = useRef(false)
  const logoutLock = useRef(false)
  const reconciliationPending = useRef(false)
  const reconciliationLock = useRef(false)

  const establishSession = useCallback((authenticatedUser: AuthUserDto) => {
    nextSessionGeneration.current += 1
    setUser(authenticatedUser)
    setSessionIdentity({ generation: nextSessionGeneration.current })
    setStatus('authenticated')
  }, [])

  const loadSession = useCallback(async (requestId: number) => {
    try {
      const restoredUser = await service.restoreSession()
      if (!operationGuard.current.isCurrent(requestId)) return
      if (restoredUser) establishSession(restoredUser)
      else {
        setUser(null)
        setSessionIdentity(null)
        setStatus('unauthenticated')
      }
    } catch (error) {
      if (!operationGuard.current.isCurrent(requestId)) return
      setUser(null)
      setSessionIdentity(null)
      setStatus('restore-error')
      setAuthError(errorMessage(error))
    }
  }, [establishSession, service])

  const retrySessionReconciliation = useCallback(async () => {
    if (!reconciliationPending.current || reconciliationLock.current) return
    reconciliationLock.current = true
    const requestId = operationGuard.current.begin()
    setStatus('reconciling')
    setUser(null)
    setSessionIdentity(null)
    setAuthError(null)
    try {
      const restoredUser = await service.restoreSession()
      if (!operationGuard.current.isCurrent(requestId)) return
      reconciliationPending.current = false
      if (restoredUser) establishSession(restoredUser)
      else {
        setUser(null)
        setSessionIdentity(null)
        setStatus('unauthenticated')
      }
    } catch {
      if (!operationGuard.current.isCurrent(requestId)) return
      setStatus('reconciliation-error')
      setAuthError(RECONCILIATION_MESSAGE)
    } finally {
      reconciliationLock.current = false
    }
  }, [establishSession, service])

  const retrySessionRestore = useCallback(async () => {
    // An accepted credential request must be reconciled through the dedicated
    // flow so a confirmed 401 also releases the credential-submission guard.
    if (reconciliationPending.current) {
      await retrySessionReconciliation()
      return
    }

    const requestId = operationGuard.current.begin()
    setStatus('restoring')
    setUser(null)
    setSessionIdentity(null)
    setAuthError(null)
    setIsLoggingOut(false)
    await loadSession(requestId)
  }, [loadSession, retrySessionReconciliation])

  useEffect(() => {
    const guard = operationGuard.current
    guard.activate()
    const requestId = guard.begin()
    void loadSession(requestId)
    return () => guard.invalidate()
  }, [loadSession])

  const login = useCallback(async (email: string, password: string) => {
    if (submitLock.current || reconciliationPending.current) return
    submitLock.current = true
    const requestId = operationGuard.current.begin()
    setIsSubmitting(true)
    setAuthError(null)
    try {
      const authenticatedUser = await service.login({ email: email.trim(), password })
      if (!operationGuard.current.isCurrent(requestId)) return
      establishSession(authenticatedUser)
    } catch (error) {
      if (!operationGuard.current.isCurrent(requestId)) return
      setUser(null)
      setSessionIdentity(null)
      if (error instanceof AuthFinalizationError) {
        reconciliationPending.current = true
        setStatus('reconciliation-error')
        setAuthError(RECONCILIATION_MESSAGE)
      } else {
        setStatus('unauthenticated')
        setAuthError(errorMessage(error))
      }
    } finally {
      submitLock.current = false
      if (operationGuard.current.isCurrent(requestId)) setIsSubmitting(false)
    }
  }, [establishSession, service])

  const register = useCallback(async (input: {
    email: string
    password: string
    display_name: string
    account_type: 'cash' | 'bank' | 'wallet'
  }) => {
    if (submitLock.current || reconciliationPending.current) return
    submitLock.current = true
    const requestId = operationGuard.current.begin()
    setIsSubmitting(true)
    setAuthError(null)
    try {
      const authenticatedUser = await service.register({
        ...input,
        email: input.email.trim(),
        display_name: input.display_name.trim(),
      })
      if (!operationGuard.current.isCurrent(requestId)) return
      establishSession(authenticatedUser)
    } catch (error) {
      if (!operationGuard.current.isCurrent(requestId)) return
      setUser(null)
      setSessionIdentity(null)
      if (error instanceof AuthFinalizationError) {
        reconciliationPending.current = true
        setStatus('reconciliation-error')
        setAuthError(RECONCILIATION_MESSAGE)
      } else {
        setStatus('unauthenticated')
        setAuthError(errorMessage(error))
      }
    } finally {
      submitLock.current = false
      if (operationGuard.current.isCurrent(requestId)) setIsSubmitting(false)
    }
  }, [establishSession, service])

  const logout = useCallback(async () => {
    // Do not supersede an in-flight session reconciliation. That request is
    // the only operation that can establish whether the server session exists.
    if (logoutLock.current || reconciliationPending.current) return
    logoutLock.current = true
    const requestId = operationGuard.current.begin()
    setIsLoggingOut(true)
    setAuthError(null)
    try {
      await service.logout()
      if (!operationGuard.current.isCurrent(requestId)) return
      setUser(null)
      setSessionIdentity(null)
      setStatus('unauthenticated')
      reconciliationPending.current = false
    } catch (error) {
      if (!operationGuard.current.isCurrent(requestId)) return
      setAuthError(errorMessage(error))
    } finally {
      logoutLock.current = false
      if (operationGuard.current.isCurrent(requestId)) setIsLoggingOut(false)
    }
  }, [service])

  const clearAuthError = useCallback(() => setAuthError(null), [])

  const value = useMemo<AuthContextValue>(() => ({
    status,
    user,
    sessionIdentity,
    authError,
    isSubmitting,
    isLoggingOut,
    retrySessionRestore,
    retrySessionReconciliation,
    login,
    register,
    logout,
    clearAuthError,
  }), [
    status,
    user,
    sessionIdentity,
    authError,
    isSubmitting,
    isLoggingOut,
    retrySessionRestore,
    retrySessionReconciliation,
    login,
    register,
    logout,
    clearAuthError,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
