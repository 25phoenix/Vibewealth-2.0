import type { BudgetCreateInput, BudgetDto, BudgetUpdateInput } from '@/types/api'
import { apiClient, type ApiClient } from './apiClient'
import { parseBudgetDto, parseBudgetListDto } from './responseSchemas'

export class BudgetsApi {
  private readonly client: ApiClient
  constructor(client: ApiClient = apiClient) { this.client = client }

  list(monthStart?: string): Promise<BudgetDto[]> {
    const query = monthStart ? `?month_start=${encodeURIComponent(monthStart)}` : ''
    return this.client.request(`/api/budgets${query}`, { parseResponse: parseBudgetListDto })
  }

  get(id: string): Promise<BudgetDto> {
    return this.client.request(`/api/budgets/${encodeURIComponent(id)}`, { parseResponse: parseBudgetDto })
  }

  create(input: BudgetCreateInput): Promise<BudgetDto> {
    return this.client.request('/api/budgets', { method: 'POST', body: input, parseResponse: parseBudgetDto })
  }

  update(id: string, input: BudgetUpdateInput): Promise<BudgetDto> {
    return this.client.request(`/api/budgets/${encodeURIComponent(id)}`, { method: 'PATCH', body: input, parseResponse: parseBudgetDto })
  }

  async delete(id: string): Promise<void> {
    await this.client.request(`/api/budgets/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }
}

export const budgetsApi = new BudgetsApi()
