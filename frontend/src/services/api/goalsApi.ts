import type { GoalCreateInput, GoalDto, GoalEntryListDto, GoalListDto, GoalMoneyMutationDto, GoalUpdateInput } from '@/types/api'
import { ApiContractError, apiClient, type ApiClient } from './apiClient'
import { parseGoalDto, parseGoalEntryListDto, parseGoalListDto, parseGoalMoneyMutationDto } from './responseSchemas'

export class GoalAllocationOutcomeUnknownError extends Error {
  constructor(error: ApiContractError, operation: 'contribution' | 'withdrawal') {
    super(`${error.message} The ${operation} may have been saved. Close this dialog and review goal history before trying again.`, { cause: error })
    this.name = 'GoalAllocationOutcomeUnknownError'
  }
}

export class GoalsApi {
  private readonly client: ApiClient
  constructor(client: ApiClient = apiClient) { this.client = client }

  list(offset = 0, limit = 50): Promise<GoalListDto> {
    return this.client.request(`/api/goals?${new URLSearchParams({ offset: String(offset), limit: String(limit) })}`, { parseResponse: parseGoalListDto })
  }

  get(id: string): Promise<GoalDto> {
    return this.client.request(`/api/goals/${encodeURIComponent(id)}`, { parseResponse: parseGoalDto })
  }

  create(input: GoalCreateInput): Promise<GoalDto> {
    return this.client.request('/api/goals', { method: 'POST', body: input, parseResponse: parseGoalDto })
  }

  update(id: string, input: GoalUpdateInput): Promise<GoalDto> {
    return this.client.request(`/api/goals/${encodeURIComponent(id)}`, { method: 'PATCH', body: input, parseResponse: parseGoalDto })
  }

  async delete(id: string): Promise<void> {
    await this.client.request(`/api/goals/${encodeURIComponent(id)}`, { method: 'DELETE' })
  }

  entries(id: string, offset = 0, limit = 50): Promise<GoalEntryListDto> {
    const query = new URLSearchParams({ offset: String(offset), limit: String(limit) })
    return this.client.request(`/api/goals/${encodeURIComponent(id)}/entries?${query}`, { parseResponse: parseGoalEntryListDto })
  }

  contribute(id: string, accountId: string, amountPaise: number): Promise<GoalMoneyMutationDto> {
    return this.allocate(id, 'contributions', accountId, amountPaise)
  }

  withdraw(id: string, accountId: string, amountPaise: number): Promise<GoalMoneyMutationDto> {
    return this.allocate(id, 'withdrawals', accountId, amountPaise)
  }

  private async allocate(id: string, operation: 'contributions' | 'withdrawals', accountId: string, amountPaise: number): Promise<GoalMoneyMutationDto> {
    try {
      return await this.client.request(`/api/goals/${encodeURIComponent(id)}/${operation}`, { method: 'POST', body: { account_id: accountId, amount_paise: amountPaise }, parseResponse: parseGoalMoneyMutationDto })
    } catch (error) {
      // Validation follows a successful HTTP response; it cannot prove rollback.
      if (error instanceof ApiContractError) throw new GoalAllocationOutcomeUnknownError(error, operation === 'withdrawals' ? 'withdrawal' : 'contribution')
      throw error
    }
  }
}

export const goalsApi = new GoalsApi()
