import type { AccountDto } from '@/types/api'
import { apiClient, type ApiClient } from './apiClient'
import { parseAccountDto, parseAccountListDto } from './responseSchemas'

export class AccountsApi {
  private readonly client: ApiClient

  constructor(client: ApiClient = apiClient) {
    this.client = client
  }

  list(): Promise<AccountDto[]> {
    return this.client.request('/api/accounts', { parseResponse: parseAccountListDto })
  }

  get(accountId: string): Promise<AccountDto> {
    return this.client.request(`/api/accounts/${encodeURIComponent(accountId)}`, { parseResponse: parseAccountDto })
  }
}

export const accountsApi = new AccountsApi()
