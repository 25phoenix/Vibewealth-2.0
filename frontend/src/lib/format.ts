import type { CurrencyCode } from '@/types/preferences'

export function formatCurrency(amountPaise: number, currency: CurrencyCode = 'INR') {
  return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(amountPaise / 100)
}

export function formatDate(date: string, options?: Intl.DateTimeFormatOptions) {
  const parsedDate = new Date(`${date}T00:00:00`)
  return new Intl.DateTimeFormat('en-IN', options ?? { day: 'numeric', month: 'short', year: 'numeric' }).format(parsedDate)
}

export function formatMonth(month: string) {
  const [year, monthNumber] = month.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' }).format(new Date(year, monthNumber - 1, 1))
}

export function getCurrentMonthKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function getTodayDateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function isValidDateKey(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
}
