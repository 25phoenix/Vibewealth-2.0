export const DEFAULT_API_BASE_URL = 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly retryAfter: number | null
  readonly currentTurn: unknown

  constructor(status: number, message: string, code: string | null = null, retryAfter: number | null = null, currentTurn: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
    this.currentTurn = currentTurn
  }
}

export class ApiNetworkError extends Error {
  constructor() {
    super('Unable to reach VibeWealth. Check that the backend is running and try again.')
    this.name = 'ApiNetworkError'
  }
}

export class ApiCsrfError extends Error {
  constructor() {
    super('This authenticated request requires a CSRF token. Restore the session and try again.')
    this.name = 'ApiCsrfError'
  }
}

export class ApiContractError extends Error {
  constructor(contract: string) {
    super(`The server returned an invalid ${contract} response.`)
    this.name = 'ApiContractError'
  }
}

export class ApiUrlError extends Error {
  constructor() {
    super('The API request URL must use the configured API origin.')
    this.name = 'ApiUrlError'
  }
}

export type ApiResponseParser<T> = (payload: unknown) => T

export interface ApiRequestOptions extends Omit<RequestInit, 'body' | 'credentials'> {
  body?: unknown
  parseError?: (payload: unknown, status: number) => { code: string; detail: string; currentTurn: unknown }
}

type FetchImplementation = typeof fetch

export function getApiBaseUrl(configured = import.meta.env.VITE_API_BASE_URL): string {
  const value = configured?.trim() || DEFAULT_API_BASE_URL
  return value.replace(/\/+$/, '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function safeDetail(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const message = value.trim()
  if (!message || /traceback|\bFile ["']|\.py:\d+/i.test(message)) return undefined
  return message.slice(0, 500)
}

function validationMessages(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (!isRecord(item)) return []
    const message = safeDetail(item.msg)
    if (!message) return []
    const location = Array.isArray(item.loc)
      ? item.loc.filter((part): part is string | number => typeof part === 'string' || typeof part === 'number')
      : []
    const field = location.filter((part) => part !== 'body').join('.')
    return [field ? `${field}: ${message}` : message]
  })
}

function errorMessage(payload: unknown, status: number): string {
  if (status >= 500) return 'The server could not complete the request. Please try again.'
  if (isRecord(payload)) {
    const detail = safeDetail(payload.detail)
    if (detail) return detail
    const messages = validationMessages(payload.detail)
    if (messages.length > 0) return messages.join(' ')
  }
  if (status === 401) return 'Your session is no longer valid. Please sign in again.'
  return `The request could not be completed (HTTP ${status}).`
}

async function readJson(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined
  let text: string
  try {
    text = await response.text()
  } catch {
    throw new ApiNetworkError()
  }
  if (!text.trim()) return undefined
  try {
    return JSON.parse(text) as unknown
  } catch {
    return undefined
  }
}

export class ApiClient {
  readonly baseUrl: string
  private readonly fetchImpl: FetchImplementation
  private csrfToken: string | null = null
  private csrfGeneration = 0
  private csrfRefreshHandler: (() => Promise<void>) | null = null
  private csrfRefreshPromise: Promise<void> | null = null

  constructor(
    baseUrl = getApiBaseUrl(),
    fetchImpl: FetchImplementation = fetch,
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, '')
    // Browser fetch requires a global receiver, not this ApiClient instance.
    this.fetchImpl = fetchImpl.bind(globalThis)
  }

  setCsrfToken(token: string): void {
    this.csrfToken = token
    this.csrfGeneration += 1
  }

  hasCsrfToken(): boolean {
    return this.csrfToken !== null
  }

  clearCsrfToken(): void {
    this.csrfToken = null
    this.csrfGeneration += 1
  }

  setCsrfRefreshHandler(handler: () => Promise<void>): void {
    this.csrfRefreshHandler = handler
  }

  refreshCsrfToken(): Promise<void> {
    if (this.csrfRefreshPromise) return this.csrfRefreshPromise
    if (!this.csrfRefreshHandler) return Promise.reject(new ApiCsrfError())

    const pending = this.csrfRefreshHandler()
    this.csrfRefreshPromise = pending
    const clearPending = () => {
      if (this.csrfRefreshPromise === pending) this.csrfRefreshPromise = null
    }
    void pending.then(clearPending, clearPending)
    return pending
  }

  async request<T>(
    path: string,
    options: ApiRequestOptions & { parseResponse: ApiResponseParser<T> },
  ): Promise<T>
  async request(path: string, options?: ApiRequestOptions): Promise<unknown>
  async request(
    path: string,
    options: ApiRequestOptions & { parseResponse?: ApiResponseParser<unknown> } = {},
  ): Promise<unknown> {
    let url: URL
    let apiOrigin: string
    try {
      url = new URL(path, `${this.baseUrl}/`)
      apiOrigin = new URL(this.baseUrl).origin
    } catch {
      throw new ApiUrlError()
    }
    if (url.origin !== apiOrigin) throw new ApiUrlError()

    const {
      body,
      parseResponse,
      parseError,
      headers: suppliedHeaders,
      method: suppliedMethod,
      ...requestOptions
    } = options
    const method = (suppliedMethod ?? 'GET').toUpperCase()
    const headers = new Headers(suppliedHeaders)
    const hasBody = body !== undefined
    if (hasBody) headers.set('Content-Type', 'application/json')

    const isSafeMethod = ['GET', 'HEAD', 'OPTIONS'].includes(method)
    const isPublicAuthRequest = url.origin === apiOrigin
      && method === 'POST'
      && ['/api/auth/login', '/api/auth/register'].includes(url.pathname)
    const csrfToken = this.csrfToken
    const csrfGeneration = this.csrfGeneration

    if (!isSafeMethod && !isPublicAuthRequest) {
      if (!csrfToken) throw new ApiCsrfError()
      headers.set('X-CSRF-Token', csrfToken)
    }

    let response: Response
    try {
      response = await this.fetchImpl(url, {
        ...requestOptions,
        redirect: 'error',
        method,
        headers,
        body: hasBody ? JSON.stringify(body) : undefined,
        credentials: 'include',
      })
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error
      throw new ApiNetworkError()
    }

    const payload = await readJson(response)
    if (!response.ok) {
      const validatedError = parseError?.(payload, response.status)
      const detail = isRecord(payload) ? payload.detail : undefined
      if (
        response.status === 403
        && detail === 'CSRF validation failed'
        && !isSafeMethod
        && !isPublicAuthRequest
      ) {
        if (csrfGeneration === this.csrfGeneration) {
          if (!this.csrfRefreshHandler) {
            throw new ApiError(response.status, errorMessage(payload, response.status), validatedError?.code ?? null, null, validatedError?.currentTurn ?? null)
          }
          await this.refreshCsrfToken()
        }
        throw new ApiError(
          403,
          'The security token was refreshed. Please submit the action again.',
          validatedError?.code ?? null, null, validatedError?.currentTurn ?? null,
        )
      }
      const code = isRecord(payload) && typeof payload.code === 'string' && /^[A-Z_]{1,80}$/.test(payload.code) ? payload.code : null
      const retryHeader = response.headers.get('Retry-After')
      const retryAfter = retryHeader && /^\d{1,5}$/.test(retryHeader) ? Math.max(1, Number(retryHeader)) : null
      throw new ApiError(response.status, validatedError?.detail ?? errorMessage(payload, response.status), validatedError?.code ?? code, retryAfter, validatedError?.currentTurn ?? null)
    }
    return parseResponse ? parseResponse(payload) : payload
  }

}

export const apiClient = new ApiClient()
