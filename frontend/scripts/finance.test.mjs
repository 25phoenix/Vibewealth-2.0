import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, before, test } from 'node:test'
import { createServer } from 'vite'

let server
let MockFinanceRepository
let MockAssistantService
let calculations
let getCurrentMonthKey
let getTodayDateKey

before(async () => {
  server = await createServer({ configFile: 'vite.config.ts', server: { middlewareMode: true }, appType: 'custom' })
  const [repositoryModule, assistantModule, calculationModule, formatModule] = await Promise.all([
    server.ssrLoadModule('/src/services/mockFinanceRepository.ts'),
    server.ssrLoadModule('/src/services/mockAssistantService.ts'),
    server.ssrLoadModule('/src/services/financeCalculations.ts'),
    server.ssrLoadModule('/src/lib/format.ts'),
  ])
  MockFinanceRepository = repositoryModule.MockFinanceRepository
  MockAssistantService = assistantModule.MockAssistantService
  calculations = calculationModule
  getCurrentMonthKey = formatModule.getCurrentMonthKey
  getTodayDateKey = formatModule.getTodayDateKey
})

after(async () => {
  await server?.close()
})

function currentDraft(overrides = {}) {
  return {
    description: 'Test transaction',
    amountPaise: 2500,
    type: 'expense',
    category: 'Other',
    date: getTodayDateKey(),
    ...overrides,
  }
}

function nextDate() {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

test('repository loads and keeps transaction, budget, and goal CRUD asynchronous', async () => {
  const repository = new MockFinanceRepository()
  await assert.doesNotReject(repository.load())
  const initialCount = repository.getSnapshot().transactions.length
  await repository.addTransaction(currentDraft())
  assert.equal(repository.getSnapshot().transactions.length, initialCount + 1)
  const transaction = repository.getSnapshot().transactions[0]
  await repository.updateTransaction(transaction.id, currentDraft({ description: 'Updated transaction' }))
  assert.equal(repository.getSnapshot().transactions[0].description, 'Updated transaction')
  await repository.deleteTransaction(transaction.id)
  assert.equal(repository.getSnapshot().transactions.length, initialCount)

  const month = getCurrentMonthKey()
  await repository.addBudget({ category: 'Education', limitPaise: 50000, month })
  const budget = repository.getSnapshot().budgets.find((item) => item.category === 'Education')
  await repository.updateBudget(budget.id, { ...budget, limitPaise: 60000 })
  assert.equal(repository.getSnapshot().budgets.find((item) => item.id === budget.id).limitPaise, 60000)
  await repository.deleteBudget(budget.id)
  assert.equal(repository.getSnapshot().budgets.some((item) => item.id === budget.id), false)

  await repository.addGoal({ name: 'Test goal', targetPaise: 100000, targetDate: '2030-01-01' })
  const goal = repository.getSnapshot().goals[0]
  await repository.moveGoalMoney(goal.id, 2500, 'add')
  assert.equal(repository.getSnapshot().goals[0].savedPaise, 2500)
  await repository.moveGoalMoney(goal.id, 500, 'withdraw')
  assert.equal(repository.getSnapshot().goals[0].savedPaise, 2000)
  await repository.updateGoal(goal.id, { ...goal, name: 'Renamed goal' })
  assert.equal(repository.getSnapshot().goals[0].name, 'Renamed goal')
  await repository.deleteGoal(goal.id)
  assert.equal(repository.getSnapshot().goals.some((item) => item.id === goal.id), false)
})

test('repository rejects invalid money and future ordinary transactions', async () => {
  const repository = new MockFinanceRepository()
  for (const amountPaise of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    await assert.rejects(repository.addTransaction(currentDraft({ amountPaise })), /positive safe integer/)
  }
  await assert.rejects(repository.addTransaction(currentDraft({ date: nextDate() })), /no later than today/)
  await assert.rejects(repository.addTransaction(currentDraft({ category: 'Salary' })), /category that matches/)
  await assert.rejects(repository.moveGoalMoney('goal-emergency', 0, 'add'), /positive safe integer/)
  await assert.rejects(repository.moveGoalMoney('goal-emergency', Number.MAX_SAFE_INTEGER, 'withdraw'), /exceeds/)
})

test('repository enforces budget category and month uniqueness and safe amounts', async () => {
  const repository = new MockFinanceRepository()
  const month = getCurrentMonthKey()
  await assert.rejects(repository.addBudget({ category: 'Housing', limitPaise: 50000, month }), /already exists/)
  await assert.rejects(repository.addBudget({ category: 'Salary', limitPaise: 50000, month }), /expense category/)
  await assert.rejects(repository.addBudget({ category: 'Education', limitPaise: Number.MAX_SAFE_INTEGER + 1, month }), /positive safe integer/)
  await assert.rejects(repository.addBudget({ category: 'Education', limitPaise: 50000, month: '2026-13' }), /YYYY-MM/)
  await assert.rejects(repository.addGoal({ name: 'Invalid goal', targetPaise: 0, targetDate: '2030-01-01' }), /positive safe integer/)
  await assert.rejects(repository.addGoal({ name: 'Invalid date', targetPaise: 10000, targetDate: '2030-02-30' }), /valid date/)
})

test('transaction filtering combines search, type, category, and inclusive date range', async () => {
  const repository = new MockFinanceRepository()
  const today = getTodayDateKey()
  await repository.addTransaction(currentDraft({ description: 'Coffee shop', amountPaise: 4200, category: 'Food & dining', notes: 'Breakfast' }))
  await repository.addTransaction(currentDraft({ description: 'Monthly salary', amountPaise: 100000, type: 'income', category: 'Salary' }))
  const matches = calculations.filterTransactions(repository.getSnapshot().transactions, {
    search: 'coffee', type: 'expense', category: 'Food & dining', from: today, to: today, sortBy: 'amount-desc',
  })
  assert.equal(matches.length, 1)
  assert.equal(matches[0].description, 'Coffee shop')
  const summary = calculations.summarizeTransactions(matches, today, today)
  assert.equal(summary.expensesPaise, 4200)
  assert.equal(summary.netPaise, -4200)
})

test('monthly and budget calculations exclude future activity and reconcile budget coverage', () => {
  const repository = new MockFinanceRepository()
  const snapshot = repository.getSnapshot()
  const month = getCurrentMonthKey()
  const today = getTodayDateKey()
  const future = nextDate()
  const extended = {
    ...snapshot,
    transactions: [...snapshot.transactions, {
      id: 'future-expense', description: 'Future purchase', amountPaise: 100000,
      type: 'expense', category: 'Education', date: future,
    }],
  }
  const summary = calculations.getMonthlySummary(extended, month, today)
  assert.equal(summary.expensesPaise, 4218000)
  const budgets = calculations.getBudgetProgress(extended, month, today)
  const overview = calculations.getBudgetOverview(extended, budgets, month, today)
  assert.equal(overview.budgetedCategorySpendingPaise, 4218000)
  assert.equal(overview.unbudgetedCategorySpendingPaise, 0)
  assert.equal(overview.totalActualSpendingPaise, 4218000)
  assert.equal(overview.allocatedPaise, budgets.reduce((total, item) => total + item.limitPaise, 0))

  extended.transactions.push({
    id: 'completed-unbudgeted', description: 'Course materials', amountPaise: 12500,
    type: 'expense', category: 'Education', date: today,
  })
  const updatedBudgets = calculations.getBudgetProgress(extended, month, today)
  const updatedOverview = calculations.getBudgetOverview(extended, updatedBudgets, month, today)
  assert.equal(updatedOverview.budgetedCategorySpendingPaise, 4218000)
  assert.equal(updatedOverview.unbudgetedCategorySpendingPaise, 12500)
  assert.equal(updatedOverview.totalActualSpendingPaise, 4230500)
  assert.equal(updatedOverview.totalActualSpendingPaise, updatedOverview.budgetedCategorySpendingPaise + updatedOverview.unbudgetedCategorySpendingPaise)
})

test('goal allocations remain outside ordinary transaction totals', async () => {
  const repository = new MockFinanceRepository()
  const before = repository.getSnapshot().transactions.length
  await repository.moveGoalMoney('goal-emergency', 10000, 'add')
  assert.equal(repository.getSnapshot().transactions.length, before)
  assert.equal(repository.getSnapshot().goals.find((goal) => goal.id === 'goal-emergency').savedPaise, 11210000)
})

test('mock assistant implements the asynchronous assistant service contract', async () => {
  const repository = new MockFinanceRepository()
  const assistant = new MockAssistantService(repository, 0)
  const reply = await assistant.reply('Where did my money go this month?')
  assert.match(reply, /sample data/)
  assert.match(reply, /INR|₹/)
})

test('all six page modules can be loaded by Vite', async () => {
  const pagePaths = [
    '/src/pages/DashboardPage.tsx',
    '/src/pages/TransactionsPage.tsx',
    '/src/pages/BudgetsPage.tsx',
    '/src/pages/SavingsGoalsPage.tsx',
    '/src/pages/AssistantPage.tsx',
    '/src/pages/SettingsPage.tsx',
  ]
  const modules = await Promise.all(pagePaths.map((path) => server.ssrLoadModule(path)))
  assert.equal(modules.length, 6)
  assert.ok(modules.every((module) => Object.values(module).some((value) => typeof value === 'function')))
})

test('frontend source is valid UTF-8 and contains no known mojibake markers', async () => {
  const sourceRoot = fileURLToPath(new URL('../src/', import.meta.url))
  const sourceFiles = []
  async function collect(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name)
      if (entry.isDirectory()) await collect(path)
      else if (/\.(?:ts|tsx|css|svg)$/.test(entry.name)) sourceFiles.push(path)
    }
  }
  await collect(sourceRoot)
  const markers = ['\u00e2\u20ac\u2122', '\u00e2\u20ac\u00a6', '\u00e2\u201a\u00b9', '\u00e2\u02c6\u2019', '\u00c2\u00b7', '\ufffd']
  for (const path of sourceFiles) {
    const bytes = await readFile(path)
    const source = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
    for (const marker of markers) assert.equal(source.includes(marker), false, `${path} contains a corrupted text marker`)
  }
})
