import type { BudgetDraft, FinanceSnapshot, SavingsGoalDraft, TransactionDraft } from '@/types/finance'
import { getTodayDateKey, isValidDateKey } from '@/lib/format'

export class FinanceValidationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FinanceValidationError'
  }
}

export function assertPositivePaise(amountPaise: number, label: string) {
  if (!Number.isSafeInteger(amountPaise) || amountPaise <= 0) {
    throw new FinanceValidationError(`${label} must be a positive safe integer amount in paise.`)
  }
}

export function validateTransactionDraft(
  draft: TransactionDraft,
  snapshot: FinanceSnapshot,
  today = getTodayDateKey(),
): TransactionDraft {
  assertPositivePaise(draft.amountPaise, 'Transaction amount')
  if (draft.type !== 'income' && draft.type !== 'expense') {
    throw new FinanceValidationError('Transaction type must be income or expense.')
  }
  if (!draft.description.trim() || draft.description.trim().length > 120) {
    throw new FinanceValidationError('Transaction description must contain 1 to 120 characters.')
  }
  if (!isValidDateKey(draft.date) || draft.date > today) {
    throw new FinanceValidationError('Transaction date must be a valid date no later than today.')
  }
  if (draft.notes && draft.notes.length > 300) {
    throw new FinanceValidationError('Transaction notes must be 300 characters or fewer.')
  }
  const category = snapshot.categories.find((item) => item.name === draft.category)
  if (!category || (category.type !== 'both' && category.type !== draft.type)) {
    throw new FinanceValidationError('Choose a category that matches the transaction type.')
  }
  return { ...draft, description: draft.description.trim(), notes: draft.notes?.trim() || undefined }
}

function validateMonth(month: string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) {
    throw new FinanceValidationError('Budget month must use YYYY-MM format.')
  }
}

export function validateBudgetDraft(draft: BudgetDraft, snapshot: FinanceSnapshot, editingId?: string): BudgetDraft {
  assertPositivePaise(draft.limitPaise, 'Budget limit')
  validateMonth(draft.month)
  const category = snapshot.categories.find((item) => item.name === draft.category && item.type !== 'income')
  if (!category) throw new FinanceValidationError('Choose a valid expense category for this budget.')
  if (snapshot.budgets.some((item) => item.month === draft.month && item.category === draft.category && item.id !== editingId)) {
    throw new FinanceValidationError('A budget already exists for this category and month.')
  }
  return { ...draft }
}

export function validateSavingsGoalDraft(draft: SavingsGoalDraft): SavingsGoalDraft {
  assertPositivePaise(draft.targetPaise, 'Goal target')
  if (!draft.name.trim() || draft.name.trim().length > 60) {
    throw new FinanceValidationError('Goal name must contain 1 to 60 characters.')
  }
  if (!isValidDateKey(draft.targetDate)) throw new FinanceValidationError('Goal target date must be a valid date.')
  return { ...draft, name: draft.name.trim() }
}
