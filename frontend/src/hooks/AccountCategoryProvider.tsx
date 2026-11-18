import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, ApiNetworkError } from '@/services/api/apiClient'
import { accountsApi } from '@/services/api/accountsApi'
import { categoriesApi } from '@/services/api/categoriesApi'
import type { AccountDto, CategoryDto } from '@/types/api'
import type { AuthSessionIdentity } from '@/types/auth'
import {
  AccountCategoryContext,
  type AccountCategoryContextValue,
  type ResourceState,
} from './accountCategoryContext'

interface ListService<T> {
  list(): Promise<T[]>
}

interface ActiveCategoryListService {
  listActive(): Promise<CategoryDto[]>
}

interface AccountCategoryProviderProps {
  children: ReactNode
  sessionIdentity: AuthSessionIdentity
  onUnauthorized: () => Promise<void>
  accountsService?: ListService<AccountDto>
  categoriesService?: ActiveCategoryListService
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiNetworkError || error instanceof ApiError) return error.message
  return 'Could not load this information. Please try again.'
}

function emptyResource<T>(): ResourceState<T> {
  return { status: 'loading', data: [], error: null }
}

function AccountCategorySession({
  children,
  onUnauthorized,
  accountsService,
  categoriesService,
}: Omit<AccountCategoryProviderProps, 'sessionIdentity'>) {
  const [accounts, setAccounts] = useState<ResourceState<AccountDto>>(emptyResource)
  const [categories, setCategories] = useState<ResourceState<CategoryDto>>(emptyResource)
  const active = useRef(false)
  const accountRequest = useRef<Promise<AccountDto[]> | null>(null)
  const categoryRequest = useRef<Promise<CategoryDto[]> | null>(null)
  const loadAccounts = useCallback(async () => {
    const isRequestOwner = accountRequest.current === null
    const request = accountRequest.current ?? Promise.resolve().then(() => (accountsService ?? accountsApi).list())
    accountRequest.current = request
    try {
      const data = await request
      if (active.current) setAccounts({ status: 'success', data, error: null })
    } catch (error) {
      if (active.current) setAccounts({ status: 'error', data: [], error: errorMessage(error) })
      if (active.current && isRequestOwner && error instanceof ApiError && error.status === 401) {
        void onUnauthorized().catch(() => {})
      }
    } finally {
      if (accountRequest.current === request) accountRequest.current = null
    }
  }, [accountsService, onUnauthorized])
  const loadCategories = useCallback(async () => {
    const isRequestOwner = categoryRequest.current === null
    const request = categoryRequest.current ?? Promise.resolve().then(() => (categoriesService ?? categoriesApi).listActive())
    categoryRequest.current = request
    try {
      const data = await request
      if (active.current) setCategories({ status: 'success', data, error: null })
    } catch (error) {
      if (active.current) setCategories({ status: 'error', data: [], error: errorMessage(error) })
      if (active.current && isRequestOwner && error instanceof ApiError && error.status === 401) {
        void onUnauthorized().catch(() => {})
      }
    } finally {
      if (categoryRequest.current === request) categoryRequest.current = null
    }
  }, [categoriesService, onUnauthorized])
  const retryAccounts = useCallback(() => {
    setAccounts((current) => ({ ...current, status: 'loading', error: null }))
    return loadAccounts()
  }, [loadAccounts])
  const retryCategories = useCallback(() => {
    setCategories((current) => ({ ...current, status: 'loading', error: null }))
    return loadCategories()
  }, [loadCategories])

  useEffect(() => {
    active.current = true
    void loadAccounts()
    void loadCategories()
    return () => { active.current = false }
  }, [loadAccounts, loadCategories])

  const value = useMemo<AccountCategoryContextValue>(() => ({
    accounts,
    categories,
    retryAccounts,
    retryCategories,
  }), [accounts, categories, retryAccounts, retryCategories])

  return <AccountCategoryContext.Provider value={value}>{children}</AccountCategoryContext.Provider>
}

/** Keep each authenticated user's account and category state in its own subtree. */
export function AccountCategoryProvider(props: AccountCategoryProviderProps) {
  return <AccountCategorySession key={props.sessionIdentity.generation} {...props} />
}
