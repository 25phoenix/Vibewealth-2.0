import { formatCurrency } from '@/lib/format'
import { getCategorySpending, getMonthlySummary, getBudgetProgress } from './financeCalculations'
import type { FinanceSnapshot } from '@/types/finance'
import type { AssistantService } from './assistantService'
import type { FinanceRepository } from './financeRepository'
import { getCurrentMonthKey } from '@/lib/format'
import { financeRepository } from './mockFinanceRepository'

function previousMonthKey(month: string) {
  const [year, monthNumber] = month.split('-').map(Number)
  const date = new Date(year, monthNumber - 2, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function getMockAssistantReply(question: string, snapshot: FinanceSnapshot, month: string) {
  const normalized = question.toLowerCase()
  const summary = getMonthlySummary(snapshot, month)

  if (normalized.includes('where') || normalized.includes('money go') || normalized.includes('spending breakdown') || normalized.includes('spent this month')) {
    const categories = getCategorySpending(snapshot.transactions, month).slice(0, 3)
    if (categories.length === 0) return 'There are no expenses recorded for this month yet. Add a few transactions and I can summarize them here.'
    const details = categories.map((item) => `${item.category} (${formatCurrency(item.amountPaise)})`).join(', ')
    return `Your largest recorded categories this month are ${details}. Total expenses so far are ${formatCurrency(summary.expensesPaise)}. This is a summary of sample data.`
  }

  if (normalized.includes('budget') || normalized.includes('within')) {
    const budgets = getBudgetProgress(snapshot, month)
    if (budgets.length === 0) return 'There are no budgets set for this month. Create a budget to see how your spending compares.'
    const exceeded = budgets.filter((budget) => budget.status === 'exceeded')
    const approaching = budgets.filter((budget) => budget.status === 'approaching')
    const detail = exceeded.length > 0
      ? `${exceeded.map((budget) => budget.category).join(', ')} ${exceeded.length === 1 ? 'is' : 'are'} over the limit`
      : approaching.length > 0
        ? `${approaching.map((budget) => budget.category).join(', ')} ${approaching.length === 1 ? 'is' : 'are'} close to the limit`
        : 'all recorded categories are below 80% of their limits'
    return `You have ${budgets.length} budgets this month; ${detail}. Overall budget figures are based on your sample transactions.`
  }

  if (normalized.includes('save') || normalized.includes('savings')) {
    const amount = summary.netPaise
    return amount >= 0
      ? `Your recorded income is higher than your expenses by ${formatCurrency(amount)} this month. That is your current net cash flow in this sample, before any unrecorded or upcoming costs.`
      : `Your recorded expenses are ${formatCurrency(Math.abs(amount))} above income this month. This is a sample-data snapshot and may not include upcoming costs.`
  }

  if (normalized.includes('afford') || normalized.includes('15,000') || normalized.includes('15000') || normalized.includes('15k')) {
    const purchasePaise = 1500000
    const afterPurchase = summary.balancePaise - purchasePaise
    return `The sample balance is ${formatCurrency(summary.balancePaise)}. A ${formatCurrency(purchasePaise)} purchase would leave ${formatCurrency(afterPurchase)} in the account snapshot. This does not account for upcoming bills or savings commitments, so it is not an affordability recommendation.`
  }

  if (normalized.includes('increased') || normalized.includes('compare') || normalized.includes('most')) {
    const current = getCategorySpending(snapshot.transactions, month)
    const previous = new Map(getCategorySpending(snapshot.transactions, previousMonthKey(month)).map((item) => [item.category, item.amountPaise]))
    const changes = current
      .map((item) => ({ category: item.category, change: item.amountPaise - (previous.get(item.category) ?? 0) }))
      .sort((left, right) => right.change - left.change)
      .filter((item) => item.change > 0)
      .slice(0, 2)
    if (changes.length === 0) return 'No spending category is higher than last month in the sample records so far.'
    return `Compared with last month's sample records, the largest increases are ${changes.map((item) => `${item.category} (+${formatCurrency(item.change)})`).join(' and ')}. The current month is still in progress.`
  }

  if (normalized.includes('spend')) {
    const categories = getCategorySpending(snapshot.transactions, month).slice(0, 3)
    const details = categories.map((item) => `${item.category} (${formatCurrency(item.amountPaise)})`).join(', ')
    return categories.length === 0
      ? 'There are no expenses recorded for this month yet. Add a few transactions and I can summarize them here.'
      : `Your top spending categories are ${details}. Total expenses so far are ${formatCurrency(summary.expensesPaise)} in these sample records.`
  }

  return 'I can summarize recorded spending, check budgets, estimate this month’s net cash flow, or compare categories with last month. These replies use mock data only. Try one of the suggested questions below.'
}

export class MockAssistantService implements AssistantService {
  private readonly repository: FinanceRepository
  private readonly delayMs: number

  constructor(repository: FinanceRepository, delayMs = 550) {
    this.repository = repository
    this.delayMs = delayMs
  }

  async reply(question: string) {
    await new Promise((resolve) => setTimeout(resolve, this.delayMs))
    return getMockAssistantReply(question, this.repository.getSnapshot(), getCurrentMonthKey())
  }
}

export const mockAssistantService = new MockAssistantService(financeRepository)
