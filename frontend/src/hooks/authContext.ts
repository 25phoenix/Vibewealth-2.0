import { createContext, useContext } from 'react'
import type { AuthUserDto } from '@/types/api'
import type { AuthSessionIdentity } from '@/types/auth'

export type SessionStatus =
  | 'restoring'
  | 'restore-error'
  | 'reconciling'
  | 'reconciliation-error'
  | 'unauthenticated'
  | 'authenticated'

export interface AuthContextValue {
  status: SessionStatus
  user: AuthUserDto | null
  sessionIdentity: AuthSessionIdentity | null
  authError: string | null
  isSubmitting: boolean
  isLoggingOut: boolean
  retrySessionRestore: () => Promise<void>
  retrySessionReconciliation: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  register: (input: {
    email: string
    password: string
    display_name: string
    account_type: 'cash' | 'bank' | 'wallet'
  }) => Promise<void>
  logout: () => Promise<void>
  clearAuthError: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
