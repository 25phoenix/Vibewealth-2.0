import { ApiError } from './apiClient'

export type TransactionCreateOutcome = 'definitive-rejection' | 'idempotency-conflict' | 'unauthorized' | 'uncertain'

/** Only responses emitted by the transaction-create contract prove no row was committed. */
export function classifyTransactionCreateOutcome(error: unknown): TransactionCreateOutcome {
  if (!(error instanceof ApiError)) return 'uncertain'
  if (error.status === 422) return 'definitive-rejection'
  if (error.status === 404 && error.message === 'Account not found') return 'definitive-rejection'
  if (error.status === 409) return 'idempotency-conflict'
  if (error.status === 401) return 'unauthorized'
  return 'uncertain'
}
