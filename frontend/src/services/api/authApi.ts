import type { AuthUserDto } from '@/types/api'
import { ApiClient, ApiError, apiClient } from './apiClient'
import { parseAuthUserDto, parseCsrfTokenDto } from './responseSchemas'

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegistrationDetails extends LoginCredentials {
  display_name: string
  account_type: 'cash' | 'bank' | 'wallet'
}

export class AuthFinalizationError extends Error {
  constructor() {
    super('The server accepted the request, but the session could not be verified.')
    this.name = 'AuthFinalizationError'
  }
}

export class AuthApi {
  private restorePromise: Promise<AuthUserDto | null> | null = null
  private readonly client: ApiClient

  constructor(client: ApiClient = apiClient) {
    this.client = client
    this.client.setCsrfRefreshHandler(() => this.fetchCsrfToken())
  }

  restoreSession(): Promise<AuthUserDto | null> {
    if (this.restorePromise) return this.restorePromise
    const pending = this.loadSession()
    this.restorePromise = pending
    const clearPending = () => {
      if (this.restorePromise === pending) this.restorePromise = null
    }
    void pending.then(clearPending, clearPending)
    return pending
  }

  async login(credentials: LoginCredentials): Promise<AuthUserDto> {
    await this.client.request('/api/auth/login', {
      method: 'POST',
      body: credentials,
    })
    return this.finishAuthentication()
  }

  async register(details: RegistrationDetails): Promise<AuthUserDto> {
    await this.client.request('/api/auth/register', {
      method: 'POST',
      body: details,
    })
    return this.finishAuthentication()
  }

  async logout(): Promise<void> {
    try {
      if (!this.client.hasCsrfToken()) await this.refreshCsrfToken()
      await this.client.request('/api/auth/logout', {
        method: 'POST',
      })
      this.clear()
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        this.clear()
        return
      }
      throw error
    }
  }

  clear(): void {
    this.client.clearCsrfToken()
  }

  private async loadSession(): Promise<AuthUserDto | null> {
    let user: AuthUserDto
    try {
      user = await this.client.request('/api/auth/me', { parseResponse: parseAuthUserDto })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        this.clear()
        return null
      }
      throw error
    }

    try {
      await this.refreshCsrfToken()
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        this.clear()
        return null
      }
      throw error
    }
    return user
  }

  private async finishAuthentication(): Promise<AuthUserDto> {
    try {
      await this.refreshCsrfToken()
      const user = await this.client.request('/api/auth/me', { parseResponse: parseAuthUserDto })
      return user
    } catch {
      this.clear()
      throw new AuthFinalizationError()
    }
  }

  private refreshCsrfToken(): Promise<void> {
    return this.client.refreshCsrfToken()
  }

  private async fetchCsrfToken(): Promise<void> {
    const response = await this.client.request('/api/auth/csrf', { parseResponse: parseCsrfTokenDto })
    this.client.setCsrfToken(response.csrf_token)
  }
}

export const authApi = new AuthApi()
