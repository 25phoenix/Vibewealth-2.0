import { createContext, useContext } from 'react'
import type { AccountDto, CategoryDto } from '@/types/api'

export type ResourceState<T> = {
  status: 'loading' | 'success' | 'error'
  data: T[]
  error: string | null
}

export interface AccountCategoryContextValue {
  accounts: ResourceState<AccountDto>
  categories: ResourceState<CategoryDto>
  retryAccounts: () => Promise<void>
  retryCategories: () => Promise<void>
}

export const AccountCategoryContext = createContext<AccountCategoryContextValue | null>(null)

export function useAccountCategoryData(): AccountCategoryContextValue {
  const context = useContext(AccountCategoryContext)
  if (!context) throw new Error('useAccountCategoryData must be used inside AccountCategoryProvider.')
  return context
}
