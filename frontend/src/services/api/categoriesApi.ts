import type { CategoryDto } from '@/types/api'
import { apiClient, type ApiClient } from './apiClient'
import { parseCategoryListDto } from './responseSchemas'

export class CategoriesApi {
  private readonly client: ApiClient

  constructor(client: ApiClient = apiClient) {
    this.client = client
  }

  listActive(): Promise<CategoryDto[]> {
    return this.client.request('/api/categories', { parseResponse: parseCategoryListDto })
  }
}

export const categoriesApi = new CategoriesApi()
