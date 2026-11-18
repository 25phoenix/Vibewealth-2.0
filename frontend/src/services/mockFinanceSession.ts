import { MockAssistantService } from './mockAssistantService'
import { createMockFinanceRepository } from './mockFinanceRepository'
import type { AuthSessionIdentity } from '@/types/auth'

export interface MockFinanceSessionServices {
  repository: ReturnType<typeof createMockFinanceRepository>
  assistantService: MockAssistantService
}

const sessionServices = new WeakMap<AuthSessionIdentity, MockFinanceSessionServices>()

/** Reuse one service pair across React rerenders for a session identity. */
export function getMockFinanceSessionServices(identity: AuthSessionIdentity): MockFinanceSessionServices {
  const existing = sessionServices.get(identity)
  if (existing) return existing
  const created = createMockFinanceSessionServices()
  sessionServices.set(identity, created)
  return created
}

/** Create a new, in-memory mock service set for one authenticated session. */
export function createMockFinanceSessionServices(): MockFinanceSessionServices {
  const repository = createMockFinanceRepository()
  return {
    repository,
    assistantService: new MockAssistantService(repository),
  }
}
