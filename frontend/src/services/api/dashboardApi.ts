import type { DashboardSummaryDto } from '@/types/api'
import { apiClient, type ApiClient } from './apiClient'
import { parseDashboardSummaryDto } from './responseSchemas'

export class DashboardApi {
  private readonly client: ApiClient

  constructor(client: ApiClient = apiClient) {
    this.client = client
  }

  summary(): Promise<DashboardSummaryDto> {
    return this.client.request('/api/dashboard/summary', {
      parseResponse: parseDashboardSummaryDto,
    })
  }
}

export const dashboardApi = new DashboardApi()
