import type { CategoryOption, FinanceSnapshot, Transaction } from '@/types/finance'

const toPaise = (rupees: number) => rupees * 100
const pad = (value: number) => String(value).padStart(2, '0')

export function getMonthKey(date = new Date()) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`
}

function dateInMonth(offset: number, day: number) {
  const today = new Date()
  const date = new Date()
  date.setDate(1)
  date.setMonth(date.getMonth() + offset)
  date.setDate(offset === 0 ? Math.min(day, today.getDate()) : day)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

interface SeedEntry {
  description: string
  amount: number
  category: string
  day: number
  type: 'income' | 'expense'
}

function monthEntries(offset: number, income: number, freelance: number, expenses: SeedEntry[]): Transaction[] {
  const prefix = getMonthKey(new Date(new Date().getFullYear(), new Date().getMonth() + offset, 1))
  const entries: SeedEntry[] = [
    { description: 'Monthly salary', amount: income, category: 'Salary', day: 1, type: 'income' },
    { description: 'Freelance project', amount: freelance, category: 'Freelance', day: 3, type: 'income' },
    ...expenses,
  ]

  return entries.map((entry, index) => ({
    id: `${prefix}-${entry.type}-${index + 1}`,
    description: entry.description,
    amountPaise: toPaise(entry.amount),
    type: entry.type,
    category: entry.category,
    date: dateInMonth(offset, entry.day),
    notes: entry.type === 'income' ? 'Sample income entry' : undefined,
  }))
}

const currentMonthExpenses: SeedEntry[] = [
  { description: 'Apartment rent', amount: 16000, category: 'Housing', day: 1, type: 'expense' },
  { description: 'BigBasket', amount: 6250, category: 'Groceries', day: 2, type: 'expense' },
  { description: 'Third Wave Coffee', amount: 4200, category: 'Food & dining', day: 3, type: 'expense' },
  { description: 'Namma Metro', amount: 2680, category: 'Transport', day: 2, type: 'expense' },
  { description: 'Airtel & BESCOM', amount: 3400, category: 'Bills & utilities', day: 3, type: 'expense' },
  { description: 'Myntra', amount: 4350, category: 'Shopping', day: 3, type: 'expense' },
  { description: 'Apollo Pharmacy', amount: 1200, category: 'Health', day: 2, type: 'expense' },
  { description: 'PVR Cinemas', amount: 2100, category: 'Entertainment', day: 3, type: 'expense' },
  { description: 'Local purchases', amount: 2000, category: 'Other', day: 3, type: 'expense' },
]

const previousMonthExpenses: SeedEntry[] = [
  { description: 'Apartment rent', amount: 16000, category: 'Housing', day: 1, type: 'expense' },
  { description: 'BigBasket', amount: 7200, category: 'Groceries', day: 4, type: 'expense' },
  { description: 'Cafe Coffee Day', amount: 5200, category: 'Food & dining', day: 6, type: 'expense' },
  { description: 'Namma Metro', amount: 3000, category: 'Transport', day: 9, type: 'expense' },
  { description: 'Airtel & BESCOM', amount: 3700, category: 'Bills & utilities', day: 12, type: 'expense' },
  { description: 'Myntra', amount: 6000, category: 'Shopping', day: 17, type: 'expense' },
  { description: 'Apollo Pharmacy', amount: 1700, category: 'Health', day: 21, type: 'expense' },
  { description: 'PVR Cinemas', amount: 3300, category: 'Entertainment', day: 24, type: 'expense' },
  { description: 'Local purchases', amount: 2900, category: 'Other', day: 27, type: 'expense' },
]

const olderMonthExpenses: SeedEntry[] = [
  { description: 'Apartment rent', amount: 16000, category: 'Housing', day: 1, type: 'expense' },
  { description: 'BigBasket', amount: 5800, category: 'Groceries', day: 4, type: 'expense' },
  { description: 'Third Wave Coffee', amount: 3400, category: 'Food & dining', day: 6, type: 'expense' },
  { description: 'Namma Metro', amount: 2200, category: 'Transport', day: 9, type: 'expense' },
  { description: 'Airtel & BESCOM', amount: 3100, category: 'Bills & utilities', day: 12, type: 'expense' },
  { description: 'Myntra', amount: 4500, category: 'Shopping', day: 17, type: 'expense' },
  { description: 'Apollo Pharmacy', amount: 1000, category: 'Health', day: 21, type: 'expense' },
  { description: 'PVR Cinemas', amount: 2500, category: 'Entertainment', day: 24, type: 'expense' },
  { description: 'Local purchases', amount: 2500, category: 'Other', day: 27, type: 'expense' },
]

export const transactionCategories: CategoryOption[] = [
  { name: 'Housing', type: 'expense' },
  { name: 'Groceries', type: 'expense' },
  { name: 'Food & dining', type: 'expense' },
  { name: 'Transport', type: 'expense' },
  { name: 'Bills & utilities', type: 'expense' },
  { name: 'Shopping', type: 'expense' },
  { name: 'Health', type: 'expense' },
  { name: 'Entertainment', type: 'expense' },
  { name: 'Education', type: 'expense' },
  { name: 'Other', type: 'both' },
  { name: 'Salary', type: 'income' },
  { name: 'Freelance', type: 'income' },
]

const month = getMonthKey()

export const mockFinanceSnapshot: FinanceSnapshot = {
  openingBalancePaise: toPaise(200000),
  transactions: [
    ...monthEntries(-2, 48000, 17000, olderMonthExpenses),
    ...monthEntries(-1, 50000, 17000, previousMonthExpenses),
    ...monthEntries(0, 50000, 18400, currentMonthExpenses),
  ],
  budgets: [
    { id: 'budget-housing', category: 'Housing', limitPaise: toPaise(18000), month },
    { id: 'budget-groceries', category: 'Groceries', limitPaise: toPaise(6000), month },
    { id: 'budget-dining', category: 'Food & dining', limitPaise: toPaise(5000), month },
    { id: 'budget-transport', category: 'Transport', limitPaise: toPaise(2500), month },
    { id: 'budget-bills', category: 'Bills & utilities', limitPaise: toPaise(3000), month },
    { id: 'budget-shopping', category: 'Shopping', limitPaise: toPaise(4000), month },
    { id: 'budget-health', category: 'Health', limitPaise: toPaise(2500), month },
    { id: 'budget-entertainment', category: 'Entertainment', limitPaise: toPaise(2500), month },
    { id: 'budget-other', category: 'Other', limitPaise: toPaise(3000), month },
  ],
  goals: [
    { id: 'goal-emergency', name: 'Emergency fund', targetPaise: toPaise(300000), savedPaise: toPaise(112000), targetDate: '2027-12-31' },
    { id: 'goal-laptop', name: 'New laptop', targetPaise: toPaise(120000), savedPaise: toPaise(46000), targetDate: '2027-05-31' },
    { id: 'goal-travel', name: 'Japan trip', targetPaise: toPaise(90000), savedPaise: toPaise(28500), targetDate: '2027-10-15' },
    { id: 'goal-education', name: 'Course fund', targetPaise: toPaise(200000), savedPaise: toPaise(83000), targetDate: '2028-01-31' },
  ],
  profile: {
    name: 'Alex Morgan',
    email: 'alex.morgan@example.com',
    occupation: 'Product design student',
  },
  categories: transactionCategories,
}

export const mockMonth = month
