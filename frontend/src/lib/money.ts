import type { MoneyPaise } from '@/types/finance'

export function parseAmountToPaise(value: string): MoneyPaise | null {
  const normalized = value.trim()
  const match = normalized.match(/^(\d+)(?:\.(\d{1,2}))?$/)
  if (!match) return null

  const wholeRupees = Number(match[1])
  const paise = Number((match[2] ?? '').padEnd(2, '0'))
  const amountPaise = wholeRupees * 100 + paise
  return Number.isSafeInteger(amountPaise) && amountPaise > 0 ? amountPaise : null
}
