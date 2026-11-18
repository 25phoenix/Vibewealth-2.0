import type { AuthUserDto } from '@/types/api'

export function authenticatedDisplayName(user: AuthUserDto | null): string {
  return user?.display_name?.trim() || user?.email || 'Your account'
}

export function authenticatedFirstName(user: AuthUserDto | null): string {
  return user?.display_name?.trim().split(/\s+/)[0] || 'there'
}
