import type { CurrencyCode } from '@/types/preferences'

export function formatCurrency(amountPaise: number, currency: CurrencyCode = 'INR') {
  return new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  }).format(amountPaise / 100)
}

/** Format integer paise without converting large monetary aggregates to Number. */
export function formatPaiseExact(amountPaise: bigint) {
  const negative = amountPaise < 0n
  const absolute = negative ? -amountPaise : amountPaise
  const whole = absolute / 100n
  const fraction = String(absolute % 100n).padStart(2, '0')
  const grouped = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(whole)
  return `${negative ? '-' : ''}₹${grouped}.${fraction}`
}

export function formatBasisPoints(value: string) {
  const basisPoints = BigInt(value)
  const wholePercent = basisPoints / 100n
  const fraction = String(basisPoints % 100n).padStart(2, '0')
  return `${wholePercent}.${fraction}`
}

export function formatDate(date: string, options?: Intl.DateTimeFormatOptions) {
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(date)
  if (dateOnly && !isValidDateKey(date)) return date
  const parsedDate = dateOnly ? new Date(`${date}T00:00:00.000Z`) : new Date(date)
  const formatOptions = options ?? { day: 'numeric', month: 'short', year: 'numeric' }
  return new Intl.DateTimeFormat('en-IN', dateOnly ? { ...formatOptions, timeZone: 'UTC' } : formatOptions).format(parsedDate)
}

export function formatMonth(month: string) {
  const [year, monthNumber] = month.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(Date.UTC(year, monthNumber - 1, 1, 12)))
}

export function getCurrentMonthKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function getIndiaMonthKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}`
}

export function getIndiaMonthStart(date = new Date()) {
  return `${getIndiaMonthKey(date)}-01`
}

export function getMonthStartDateKey(monthKey: string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(monthKey)) throw new RangeError('Month must use YYYY-MM format.')
  return `${monthKey}-01`
}

export function getTodayDateKey(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function isValidDateKey(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  if (year < 1 || year > 9999) return false
  const date = new Date(0)
  date.setUTCHours(0, 0, 0, 0)
  date.setUTCFullYear(year, month - 1, day)
  return date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day
}
