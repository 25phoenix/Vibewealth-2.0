const STORAGE_PREFIX = 'vibewealth:pending-transaction:v1:'
const OPERATION_KEY_PATTERN = /^[A-Za-z0-9._~-]{16,128}$/

export interface PendingTransactionOperation {
  version: 1
  userId: string
  key: string
}

export class PendingOperationStorageError extends Error {
  constructor(message = 'Pending transaction recovery storage is unavailable.') {
    super(message)
    this.name = 'PendingOperationStorageError'
  }
}

export type PendingOperationRead =
  | { status: 'empty' }
  | { status: 'pending'; operation: PendingTransactionOperation }
  | { status: 'invalid'; recoverableKey: string | null; reason: 'malformed' | 'unsupported' | 'owner-mismatch' | 'invalid-key' }

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`
}

function getStorage(): Storage {
  if (typeof window === 'undefined') throw new PendingOperationStorageError()
  try {
    // Accessing the property itself can throw in privacy-restricted contexts.
    const storage = window.sessionStorage
    if (!storage) throw new PendingOperationStorageError()
    return storage
  } catch {
    throw new PendingOperationStorageError()
  }
}

export function readPendingTransactionOperation(userId: string): PendingOperationRead {
  const storage = getStorage()
  let serialized: string | null
  try {
    serialized = storage.getItem(storageKey(userId))
  } catch {
    throw new PendingOperationStorageError()
  }
  if (serialized === null) return { status: 'empty' }

  let value: unknown
  try {
    value = JSON.parse(serialized)
  } catch {
    return { status: 'invalid', recoverableKey: null, reason: 'malformed' }
  }
  if (typeof value !== 'object' || value === null) {
    return { status: 'invalid', recoverableKey: null, reason: 'malformed' }
  }
  const record = value as Record<string, unknown>
  const recoverableKey = typeof record.key === 'string' && OPERATION_KEY_PATTERN.test(record.key) ? record.key : null
  if (record.userId !== userId) {
    return { status: 'invalid', recoverableKey: null, reason: 'owner-mismatch' }
  }
  if (recoverableKey === null) {
    return { status: 'invalid', recoverableKey: null, reason: 'invalid-key' }
  }
  if (record.version !== 1 || Object.keys(record).some((field) => !['version', 'userId', 'key'].includes(field))) {
    return { status: 'invalid', recoverableKey, reason: 'unsupported' }
  }
  return { status: 'pending', operation: value as PendingTransactionOperation }
}

export function storePendingTransactionOperation(operation: PendingTransactionOperation): void {
  if (
    operation.version !== 1
    || !operation.userId
    || !OPERATION_KEY_PATTERN.test(operation.key)
  ) {
    throw new PendingOperationStorageError('The pending transaction operation is invalid.')
  }
  const existing = readPendingTransactionOperation(operation.userId)
  if (existing.status === 'invalid') {
    throw new PendingOperationStorageError('An unreadable pending transaction must be resolved first.')
  }
  if (existing.status === 'pending' && existing.operation.key !== operation.key) {
    throw new PendingOperationStorageError('A previous transaction is still being recovered.')
  }
  try {
    getStorage().setItem(storageKey(operation.userId), JSON.stringify(operation))
  } catch {
    throw new PendingOperationStorageError()
  }
}

export function clearPendingTransactionOperation(userId: string, key: string): void {
  const existing = readPendingTransactionOperation(userId)
  if (existing.status !== 'pending' || existing.operation.key !== key) return
  try {
    getStorage().removeItem(storageKey(userId))
  } catch {
    throw new PendingOperationStorageError()
  }
}

/** Clear a marker only after the authenticated server confirms this exact key exists. */
export function clearResolvedPendingTransactionOperation(userId: string, key: string): void {
  const storage = getStorage()
  let serialized: string | null
  try {
    serialized = storage.getItem(storageKey(userId))
  } catch {
    throw new PendingOperationStorageError()
  }
  if (serialized === null) return
  let value: unknown
  try {
    value = JSON.parse(serialized)
  } catch {
    // Leave malformed data intact; it requires explicit user reconciliation.
    return
  }
  if (typeof value === 'object' && value !== null) {
    const record = value as Record<string, unknown>
    if (record.userId === userId && record.key === key) {
      try {
        storage.removeItem(storageKey(userId))
      } catch {
        throw new PendingOperationStorageError()
      }
    }
  }
}

/** Explicitly abandon only an invalid marker; callers must obtain user confirmation. */
export function abandonInvalidPendingTransactionOperation(userId: string): void {
  const existing = readPendingTransactionOperation(userId)
  if (existing.status !== 'invalid') throw new PendingOperationStorageError('Only an unrecoverable marker can be reconciled this way.')
  try {
    getStorage().removeItem(storageKey(userId))
  } catch {
    throw new PendingOperationStorageError()
  }
}
