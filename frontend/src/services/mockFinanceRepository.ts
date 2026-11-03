import { mockFinanceSnapshot } from '@/mocks/finance'
import type {
  BudgetDraft,
  FinanceSnapshot,
  SavingsGoalDraft,
  TransactionDraft,
  UserProfile,
} from '@/types/finance'
import type { FinanceRepository } from './financeRepository'
import { assertPositivePaise, FinanceValidationError, validateBudgetDraft, validateSavingsGoalDraft, validateTransactionDraft } from './financeValidation'

function copySnapshot(snapshot: FinanceSnapshot): FinanceSnapshot {
  return {
    ...snapshot,
    transactions: snapshot.transactions.map((item) => ({ ...item })),
    budgets: snapshot.budgets.map((item) => ({ ...item })),
    goals: snapshot.goals.map((item) => ({ ...item })),
    profile: { ...snapshot.profile },
    categories: snapshot.categories.map((item) => ({ ...item })),
  }
}

export class MockFinanceRepository implements FinanceRepository {
  private snapshot = copySnapshot(mockFinanceSnapshot)
  private listeners = new Set<() => void>()
  private nextId = 1

  getSnapshot = () => this.snapshot

  async load() {}

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private commit(update: (current: FinanceSnapshot) => FinanceSnapshot) {
    this.snapshot = update(this.snapshot)
    this.listeners.forEach((listener) => listener())
  }

  private createId(prefix: string) {
    const id = `${prefix}-${this.nextId}`
    this.nextId += 1
    return id
  }

  async addTransaction(draft: TransactionDraft) {
    const transaction = { ...validateTransactionDraft(draft, this.snapshot), id: this.createId('transaction') }
    this.commit((current) => ({ ...current, transactions: [transaction, ...current.transactions] }))
  }

  async updateTransaction(id: string, draft: TransactionDraft) {
    if (!this.snapshot.transactions.some((item) => item.id === id)) throw new FinanceValidationError('Transaction not found.')
    const validated = validateTransactionDraft(draft, this.snapshot)
    this.commit((current) => ({
      ...current,
      transactions: current.transactions.map((item) => item.id === id ? { ...validated, id } : item),
    }))
  }

  async deleteTransaction(id: string) {
    if (!this.snapshot.transactions.some((item) => item.id === id)) throw new FinanceValidationError('Transaction not found.')
    this.commit((current) => ({
      ...current,
      transactions: current.transactions.filter((item) => item.id !== id),
    }))
  }

  async addBudget(draft: BudgetDraft) {
    const budget = { ...validateBudgetDraft(draft, this.snapshot), id: this.createId('budget') }
    this.commit((current) => ({ ...current, budgets: [budget, ...current.budgets] }))
  }

  async updateBudget(id: string, draft: BudgetDraft) {
    if (!this.snapshot.budgets.some((item) => item.id === id)) throw new FinanceValidationError('Budget not found.')
    const validated = validateBudgetDraft(draft, this.snapshot, id)
    this.commit((current) => ({
      ...current,
      budgets: current.budgets.map((item) => item.id === id ? { ...validated, id } : item),
    }))
  }

  async deleteBudget(id: string) {
    if (!this.snapshot.budgets.some((item) => item.id === id)) throw new FinanceValidationError('Budget not found.')
    this.commit((current) => ({ ...current, budgets: current.budgets.filter((item) => item.id !== id) }))
  }

  async addGoal(draft: SavingsGoalDraft) {
    const goal = { ...validateSavingsGoalDraft(draft), id: this.createId('goal'), savedPaise: 0 }
    this.commit((current) => ({ ...current, goals: [goal, ...current.goals] }))
  }

  async updateGoal(id: string, draft: SavingsGoalDraft) {
    if (!this.snapshot.goals.some((item) => item.id === id)) throw new FinanceValidationError('Savings goal not found.')
    const validated = validateSavingsGoalDraft(draft)
    this.commit((current) => ({
      ...current,
      goals: current.goals.map((item) => item.id === id ? { ...item, ...validated, id } : item),
    }))
  }

  async deleteGoal(id: string) {
    if (!this.snapshot.goals.some((item) => item.id === id)) throw new FinanceValidationError('Savings goal not found.')
    this.commit((current) => ({ ...current, goals: current.goals.filter((item) => item.id !== id) }))
  }

  async moveGoalMoney(id: string, amountPaise: number, direction: 'add' | 'withdraw') {
    assertPositivePaise(amountPaise, 'Goal allocation')
    if (direction !== 'add' && direction !== 'withdraw') throw new FinanceValidationError('Goal allocation direction must be add or withdraw.')
    const goal = this.snapshot.goals.find((item) => item.id === id)
    if (!goal) throw new FinanceValidationError('Savings goal not found.')
    if (direction === 'withdraw' && amountPaise > goal.savedPaise) throw new FinanceValidationError('Withdrawal exceeds the goal allocation.')
    if (direction === 'add' && !Number.isSafeInteger(goal.savedPaise + amountPaise)) {
      throw new FinanceValidationError('Goal allocation would exceed the safe integer range in paise.')
    }

    this.commit((current) => ({
      ...current,
      goals: current.goals.map((item) => item.id === id
        ? { ...item, savedPaise: item.savedPaise + (direction === 'add' ? amountPaise : -amountPaise) }
        : item),
    }))
  }

  async updateProfile(profile: UserProfile) {
    if (!profile.name.trim() || !profile.email.trim()) throw new FinanceValidationError('Profile name and email are required.')
    this.commit((current) => ({ ...current, profile: { ...profile, name: profile.name.trim(), email: profile.email.trim() } }))
  }
}

export const financeRepository = new MockFinanceRepository()
