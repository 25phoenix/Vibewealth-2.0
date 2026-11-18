import type { MoneyPaise } from '@/types/finance'

export function parseAmountToPaise(value: string): MoneyPaise | null {
  const normalized = value.trim()
  const match = normalized.match(/^(\d+)(?:\.(\d{1,2}))?$/)
  if (!match) return null
  const amountPaise = BigInt(match[1]) * 100n + BigInt((match[2] ?? '').padEnd(2, '0') || '0')
  return amountPaise > 0n && amountPaise <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(amountPaise) : null
}
