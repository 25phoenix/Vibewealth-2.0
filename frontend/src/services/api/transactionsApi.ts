import type { TransactionCreateInput, TransactionDto, TransactionListDto, TransactionListQuery } from '@/types/api'
import { ApiError, apiClient, type ApiClient } from './apiClient'
import { parseTransactionDto, parseTransactionListDto } from './responseSchemas'

export class ResolvedOperationConflictError extends Error {
  constructor() {
    super('A previous transaction operation was resolved with different details.')
    this.name = 'ResolvedOperationConflictError'
  }
}

export class TransactionsApi {
  private readonly client: ApiClient

  constructor(client: ApiClient = apiClient) {
    this.client = client
  }

  list(query: TransactionListQuery): Promise<TransactionListDto> {
    const params = new URLSearchParams()
    for (const key of [
      'account_id', 'transaction_type', 'category_id', 'date_from', 'date_to', 'offset', 'limit',
    ] as const) {
      const value = query[key]
      if (value !== undefined) params.set(key, String(value))
    }
    return this.client.request(`/api/transactions?${params.toString()}`, {
      parseResponse: parseTransactionListDto,
    })
  }

  create(input: TransactionCreateInput, idempotencyKey: string): Promise<TransactionDto> {
    return this.client.request('/api/transactions', {
      method: 'POST',
      body: input,
      headers: { 'Idempotency-Key': idempotencyKey },
      parseResponse: parseTransactionDto,
    })
  }

  async resolveOperation(idempotencyKey: string): Promise<TransactionDto | null> {
    try {
      return await this.client.request(
        `/api/transactions/operations/${encodeURIComponent(idempotencyKey)}`,
        { parseResponse: parseTransactionDto },
      )
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null
      throw error
    }
  }
}

export function createTransactionOperationKey(): string {
  const cryptoApi = globalThis.crypto
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID()
  if (!cryptoApi?.getRandomValues) {
    throw new Error('Secure transaction submission keys are unavailable in this browser.')
  }
  const bytes = cryptoApi.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export const transactionsApi = new TransactionsApi()
