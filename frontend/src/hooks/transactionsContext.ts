import { createContext, useContext } from 'react'
import type { TransactionCreateInput, TransactionDto, TransactionListDto, TransactionListQuery } from '@/types/api'

export interface TransactionListState {
  status: 'loading' | 'success' | 'error'
  data: TransactionListDto | null
  error: string | null
}

export interface TransactionsContextValue {
  list: TransactionListState
  query: TransactionListQuery
  isCreating: boolean
  mutationRevision: number
  recovery: {
    status: 'checking' | 'ready' | 'not-found' | 'error' | 'invalid' | 'recovered'
    message: string | null
    transaction: TransactionDto | null
  }
  pendingOperationKey: string | null
  setFilters: (changes: Partial<Omit<TransactionListQuery, 'offset' | 'limit'>>) => void
  setOffset: (offset: number) => void
  resetFilters: () => void
  retryList: () => Promise<void>
  retryOperationResolution: () => Promise<TransactionDto | null>
  acknowledgeRecovery: () => void
  reconcileInvalidOperation: () => boolean
  createTransaction: (input: TransactionCreateInput, idempotencyKey: string) => Promise<void>
}

export const TransactionsContext = createContext<TransactionsContextValue | null>(null)

export function useTransactions(): TransactionsContextValue {
  const context = useContext(TransactionsContext)
  if (!context) throw new Error('useTransactions must be used inside TransactionsProvider.')
  return context
}
