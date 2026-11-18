import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, ApiNetworkError } from '@/services/api/apiClient'
import { classifyTransactionCreateOutcome } from '@/services/api/transactionOutcome'
import { ResolvedOperationConflictError, transactionsApi } from '@/services/api/transactionsApi'
import {
  abandonInvalidPendingTransactionOperation,
  clearPendingTransactionOperation,
  clearResolvedPendingTransactionOperation,
  PendingOperationStorageError,
  readPendingTransactionOperation,
  storePendingTransactionOperation,
} from '@/services/api/pendingTransactionOperation'
import type { TransactionCreateInput, TransactionDto, TransactionListDto, TransactionListQuery } from '@/types/api'
import { useAccountCategoryData } from './accountCategoryContext'
import { TransactionsContext, type TransactionListState, type TransactionsContextValue } from './transactionsContext'

const DEFAULT_TRANSACTION_QUERY: TransactionListQuery = {
  offset: 0,
  limit: 50,
}

interface TransactionsProviderProps {
  children: ReactNode
  sessionGeneration: number
  userId: string
  onUnauthorized: () => Promise<void>
  service?: TransactionService
}

interface TransactionService {
  list(query: TransactionListQuery): Promise<TransactionListDto>
  create(input: TransactionCreateInput, idempotencyKey: string): Promise<TransactionDto>
  resolveOperation?(idempotencyKey: string): Promise<TransactionDto | null>
}

interface InFlightList {
  key: string
  generation: number
  promise: Promise<void>
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiNetworkError || error instanceof ApiError) return error.message
  return 'Could not load transactions. Please try again.'
}

function isUnauthorized(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 401
}

type Recovery = {
  status: 'checking' | 'ready' | 'not-found' | 'error' | 'invalid' | 'recovered'
  message: string | null
  transaction: TransactionDto | null
}

function TransactionsSession({
  children,
  userId,
  onUnauthorized,
  service,
}: Omit<TransactionsProviderProps, 'sessionGeneration'>) {
  const { retryAccounts } = useAccountCategoryData()
  const [query, setQuery] = useState(DEFAULT_TRANSACTION_QUERY)
  const [reloadVersion, setReloadVersion] = useState(0)
  const [list, setList] = useState<TransactionListState>({ status: 'loading', data: null, error: null })
  const [isCreating, setIsCreating] = useState(false)
  const [mutationRevision, setMutationRevision] = useState(0)
  const [recovery, setRecovery] = useState<Recovery>({ status: 'checking', message: null, transaction: null })
  const [pendingOperationKey, setPendingOperationKey] = useState<string | null>(null)
  const active = useRef(false)
  const generation = useRef(0)
  const inFlightList = useRef<InFlightList | null>(null)
  const createPromise = useRef<Promise<TransactionDto> | null>(null)
  const resolutionPromise = useRef<Promise<TransactionDto | null> | null>(null)
  const api = service ?? transactionsApi

  const load = useCallback((requestedQuery: TransactionListQuery): Promise<void> => {
    const key = JSON.stringify(requestedQuery)
    if (inFlightList.current?.key === key) return inFlightList.current.promise

    const requestGeneration = ++generation.current
    setList({ status: 'loading', data: null, error: null })
    const request = Promise.resolve().then(() => api.list(requestedQuery))
    const pending = (async () => {
      try {
        const data = await request
        if (active.current && generation.current === requestGeneration) {
          if (data.offset > 0 && data.items.length === 0) {
            const lastValidOffset = Math.max(0, Math.ceil(data.total / data.limit) - 1) * data.limit
            setQuery((current) => ({ ...current, offset: lastValidOffset }))
            return
          }
          setList({ status: 'success', data, error: null })
        }
      } catch (error) {
        if (active.current && generation.current === requestGeneration) {
          setList({ status: 'error', data: null, error: errorMessage(error) })
          if (isUnauthorized(error)) void onUnauthorized().catch(() => {})
        }
      } finally {
        if (inFlightList.current?.generation === requestGeneration) inFlightList.current = null
      }
    })()
    inFlightList.current = { key, generation: requestGeneration, promise: pending }
    return pending
  }, [api, onUnauthorized])

  const setFilters = useCallback((changes: Partial<Omit<TransactionListQuery, 'offset' | 'limit'>>) => {
    setQuery((current) => ({ ...current, ...changes, offset: 0 }))
  }, [])
  const setOffset = useCallback((offset: number) => {
    setQuery((current) => ({ ...current, offset: Math.max(0, offset) }))
  }, [])
  const resetFilters = useCallback(() => setQuery(DEFAULT_TRANSACTION_QUERY), [])
  const retryList = useCallback(() => load(query), [load, query])
  const invalidateListRequests = useCallback(() => {
    generation.current += 1
    inFlightList.current = null
  }, [])

  const retryOperationResolution = useCallback((): Promise<TransactionDto | null> => {
    if (resolutionPromise.current) return resolutionPromise.current
    const pending = (async (): Promise<TransactionDto | null> => {
      if (active.current) setRecovery({ status: 'checking', message: null, transaction: null })
      let saved
      try {
        saved = readPendingTransactionOperation(userId)
      } catch {
        if (active.current) {
          setRecovery({
            status: 'error',
            message: 'This tab cannot read its pending transaction recovery record. Keep this tab open and retry recovery before creating another transaction.',
            transaction: null,
          })
        }
        return null
      }

      if (saved.status === 'invalid' && !saved.recoverableKey) {
        if (active.current) {
          setPendingOperationKey(null)
          setRecovery({
            status: 'invalid',
            message: 'Automatic recovery is impossible because this tab’s saved operation marker is malformed or belongs to a different user. Inspect transaction history for a possible matching transaction before deciding whether to continue. History cannot guarantee certainty when the operation cannot be identified.',
            transaction: null,
          })
        }
        return null
      }
      if (saved.status === 'empty') {
        if (active.current) {
          setPendingOperationKey(null)
          setRecovery({ status: 'ready', message: null, transaction: null })
        }
        return null
      }

      const invalidMarker = saved.status === 'invalid'
      const key = saved.status === 'invalid' ? saved.recoverableKey! : saved.operation.key
      if (active.current) setPendingOperationKey(invalidMarker ? null : key)
      try {
        const transaction = service?.resolveOperation
          ? await service.resolveOperation(key)
          : await transactionsApi.resolveOperation(key)
        if (!active.current) return null
        if (transaction === null) {
          setRecovery(invalidMarker
            ? { status: 'invalid', message: 'The marker contains a valid operation key, but the server did not confirm a saved transaction. Keep the marker and inspect transaction history; automatic duplicate prevention for this unsupported record cannot be guaranteed.', transaction: null }
            : { status: 'not-found', message: 'No completed transaction was found. Re-enter its details to retry safely with the same pending operation.', transaction: null })
          return null
        }
        try {
          if (invalidMarker) clearResolvedPendingTransactionOperation(userId, key)
          else clearPendingTransactionOperation(userId, key)
        } catch {
          setRecovery({
            status: 'error',
            message: 'The transaction was found and saved, but its local recovery marker could not be cleared. Retry recovery before creating another transaction.',
            transaction,
          })
          return null
        }
        setPendingOperationKey(null)
        setRecovery({
          status: 'recovered',
          message: 'A previously submitted transaction was found and recovered.',
          transaction,
        })
        invalidateListRequests()
        setReloadVersion((current) => current + 1)
        void Promise.resolve().then(retryAccounts).catch(() => {})
        return transaction
      } catch (error) {
        if (!active.current) return null
        if (isUnauthorized(error)) void onUnauthorized().catch(() => {})
        setRecovery({
          status: invalidMarker ? 'invalid' : 'error',
          message: invalidMarker
            ? 'The saved operation marker could not be resolved automatically. Keep it and inspect transaction history before deciding whether to continue. If you explicitly abandon it, duplicate prevention for that operation cannot be guaranteed.'
            : isUnauthorized(error)
              ? 'Sign in again as the same user to resolve the pending transaction.'
              : errorMessage(error),
          transaction: null,
        })
        return null
      }
    })()
    resolutionPromise.current = pending
    const clearPending = () => {
      if (resolutionPromise.current === pending) resolutionPromise.current = null
    }
    void pending.then(clearPending, clearPending)
    return pending
  }, [invalidateListRequests, onUnauthorized, retryAccounts, service, userId])

  useEffect(() => {
    active.current = true
    void load(query)
    return () => { active.current = false }
  }, [load, query, reloadVersion])

  useEffect(() => {
    void retryOperationResolution()
  }, [retryOperationResolution])

  const createTransaction = useCallback((input: TransactionCreateInput, idempotencyKey: string): Promise<void> => {
    if (createPromise.current) return createPromise.current.then(() => {})
    if (recovery.status === 'checking' || recovery.status === 'invalid') {
      return Promise.reject(new PendingOperationStorageError('Resolve the pending transaction before creating another one.'))
    }
    try {
      const stored = readPendingTransactionOperation(userId)
      if (stored.status === 'invalid') throw new PendingOperationStorageError('Resolve the unreadable pending transaction first.')
      if (stored.status === 'pending' && stored.operation.key !== idempotencyKey) {
        throw new PendingOperationStorageError('Resolve the previous transaction before starting another one.')
      }
      storePendingTransactionOperation({ version: 1, userId, key: idempotencyKey })
      setPendingOperationKey(idempotencyKey)
    } catch (error) {
      setRecovery({ status: 'error', message: 'The pending operation could not be stored safely. No transaction was sent; retry recovery before creating another transaction.', transaction: null })
      return Promise.reject(error)
    }
    setIsCreating(true)
    let pending: Promise<TransactionDto>
    pending = Promise.resolve()
      .then(() => api.create(input, idempotencyKey))
      .then(async (created) => {
        try {
          clearPendingTransactionOperation(userId, idempotencyKey)
          if (active.current) {
            setPendingOperationKey(null)
            setRecovery({ status: 'ready', message: null, transaction: null })
          }
        } catch {
          if (active.current) {
            setPendingOperationKey(idempotencyKey)
            setRecovery({
              status: 'error',
              message: 'The transaction was saved, but its local recovery marker could not be cleared. Retry recovery before creating another transaction.',
              transaction: created,
            })
          }
        }
        if (active.current) {
          setMutationRevision((value) => value + 1)
          invalidateListRequests()
          setReloadVersion((current) => current + 1)
          // The POST is already committed. Refresh failures belong to their
          // own resource state and must never turn creation into a failure.
          void Promise.resolve().then(retryAccounts).catch(() => {})
        }
        return created
      })
      .catch(async (error: unknown) => {
        if (isUnauthorized(error)) {
          if (active.current) {
            setRecovery({ status: 'error', message: 'Sign in again as the same user to resolve the pending transaction.', transaction: null })
            void onUnauthorized().catch(() => {})
          }
          throw error
        }
        const outcome = classifyTransactionCreateOutcome(error)
        if (outcome === 'idempotency-conflict') {
          const recovered = await retryOperationResolution()
          if (recovered !== null) {
            const matchesSubmittedPayload = recovered.account_id === input.account_id
              && recovered.category_id === input.category_id
              && recovered.transaction_type === input.transaction_type
              && recovered.amount_paise === input.amount_paise
              && recovered.description === input.description.trim()
              && recovered.transaction_date === input.transaction_date
              && (recovered.notes ?? null) === (input.notes?.trim() || null)
            if (matchesSubmittedPayload) return recovered
            if (active.current) {
              setRecovery({
                status: 'ready',
                message: 'A previous transaction was found with different details. Review the recovered transaction before submitting these details as a new transaction.',
                transaction: recovered,
              })
            }
            throw new ResolvedOperationConflictError()
          }
          throw error
        }
        if (outcome === 'definitive-rejection') {
          try {
            clearPendingTransactionOperation(userId, idempotencyKey)
            if (active.current) {
              setPendingOperationKey(null)
              setRecovery({ status: 'ready', message: null, transaction: null })
            }
          } catch {
            if (active.current) setRecovery({ status: 'error', message: 'The request was rejected, but its local recovery marker could not be cleared. Retry recovery before creating another transaction.', transaction: null })
          }
          throw error
        }
        if (active.current) {
          setRecovery({
            status: 'error',
            message: error instanceof ApiError && error.status === 408
              ? 'The request timed out. The transaction may still have been saved; resolve or retry this same operation before creating another.'
              : 'We could not confirm whether this transaction was saved. Resolve or retry this same operation before creating another.',
            transaction: null,
          })
        }
        throw error
      })
      .finally(() => {
        if (createPromise.current === pending) {
          createPromise.current = null
          if (active.current) setIsCreating(false)
        }
      })
    createPromise.current = pending
    return pending.then(() => {})
  }, [api, invalidateListRequests, onUnauthorized, recovery.status, retryAccounts, retryOperationResolution, userId])

  const reconcileInvalidOperation = useCallback(() => {
    try {
      abandonInvalidPendingTransactionOperation(userId)
      setPendingOperationKey(null)
      setRecovery({ status: 'ready', message: 'The unrecoverable marker was explicitly abandoned. Automatic duplicate prevention cannot be guaranteed for the earlier operation.', transaction: null })
      return true
    } catch {
      setRecovery({ status: 'invalid', message: 'The marker could not be removed. It remains in this tab; retry recovery or check browser storage availability.', transaction: null })
      return false
    }
  }, [userId])

  const acknowledgeRecovery = useCallback(() => {
    if (recovery.status === 'recovered') {
      setRecovery({ status: 'ready', message: null, transaction: null })
    }
  }, [recovery.status])

  const value = useMemo<TransactionsContextValue>(() => ({
    list,
    query,
    isCreating,
    mutationRevision,
    recovery,
    pendingOperationKey,
    setFilters,
    setOffset,
    resetFilters,
    retryList,
    retryOperationResolution,
    acknowledgeRecovery,
    reconcileInvalidOperation,
    createTransaction,
  }), [list, query, isCreating, mutationRevision, recovery, pendingOperationKey, setFilters, setOffset, resetFilters, retryList, retryOperationResolution, acknowledgeRecovery, reconcileInvalidOperation, createTransaction])

  return <TransactionsContext.Provider value={value}>{children}</TransactionsContext.Provider>
}

/** Reset all transaction state whenever the authenticated session changes. */
export function TransactionsProvider(props: TransactionsProviderProps) {
  return <TransactionsSession key={props.sessionGeneration} {...props} />
}
