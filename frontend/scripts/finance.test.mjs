import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { after, before, test } from 'node:test'
import { act, createElement, StrictMode, useContext } from 'react'
import { renderToString } from 'react-dom/server'
import { JSDOM } from 'jsdom'
import { createServer } from 'vite'

let server
let moduleDom
let moduleGlobals
let MockFinanceRepository
let MockAssistantService
let calculations
let getCurrentMonthKey
let getTodayDateKey
let formatDate
let isValidDateKey
let readPendingTransactionOperation
let storePendingTransactionOperation
let abandonInvalidPendingTransactionOperation
let classifyTransactionCreateOutcome
let parseAmountToPaise
let ApiClient
let ApiError
let ApiNetworkError
let ApiCsrfError
let ApiContractError
let ApiUrlError
let getApiBaseUrl
let AuthApi
let AuthFinalizationError
let AccountsApi
let CategoriesApi
let App
let AuthContext
let AuthPage
let getMockFinanceSessionServices
let AuthOperationGuard
let AuthProvider
let useAuth
let SessionGate
let AccountCategoryProvider
let AccountCategoryContext
let useAccountCategoryData
let SettingsPage
let FinanceContext
let TransactionsApi
let parseTransactionDto
let createTransactionOperationKey
let TransactionsProvider
let TransactionsContext
let useTransactions
let TransactionsPage
let TransactionForm
let Dialog
let parseBudgetDto
let parseBudgetListDto
let parseGoalDto
let parseGoalListDto
let parseGoalEntryListDto
let formatPaiseExact
let formatBasisPoints
let BudgetsApi
let GoalsApi
let BudgetsProvider
let BudgetsContext
let SavingsGoalsProvider
let SavingsGoalsContext
let AccountCategoryContextForGoals
let GoalMoneyDialog
let getIndiaMonthKey
let getIndiaMonthStart
let getMonthStartDateKey
let DashboardApi
let parseDashboardSummaryDto
let DashboardContext
let DashboardProvider
let DashboardPage

before(async () => {
  moduleDom = new JSDOM('<!doctype html><html><body><div id="module-root"></div></body></html>', { url: 'http://localhost/', pretendToBeVisual: true })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'Event', 'MouseEvent', 'requestAnimationFrame', 'cancelAnimationFrame']
  moduleGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: moduleDom.window,
    document: moduleDom.window.document,
    navigator: moduleDom.window.navigator,
    HTMLElement: moduleDom.window.HTMLElement,
    Element: moduleDom.window.Element,
    Node: moduleDom.window.Node,
    MutationObserver: moduleDom.window.MutationObserver,
    Event: moduleDom.window.Event,
    MouseEvent: moduleDom.window.MouseEvent,
    requestAnimationFrame: moduleDom.window.requestAnimationFrame.bind(moduleDom.window),
    cancelAnimationFrame: moduleDom.window.cancelAnimationFrame.bind(moduleDom.window),
  })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }
  server = await createServer({ configFile: 'vite.config.ts', server: { middlewareMode: true }, appType: 'custom' })
  const [repositoryModule, assistantModule, calculationModule, formatModule, moneyModule, apiModule, outcomeModule, pendingOperationModule, authModule, accountsModule, categoriesModule, appModule, authContextModule, authPageModule, mockSessionModule, authGuardModule, authProviderModule, accountCategoryProviderModule, accountCategoryContextModule, settingsModule, financeContextModule, transactionsApiModule, transactionsProviderModule, transactionsContextModule, transactionsPageModule, transactionDialogModule, dialogModule, dashboardApiModule, dashboardContextModule, dashboardProviderModule, dashboardPageModule] = await Promise.all([
    server.ssrLoadModule('/src/services/mockFinanceRepository.ts'),
    server.ssrLoadModule('/src/services/mockAssistantService.ts'),
    server.ssrLoadModule('/src/services/financeCalculations.ts'),
    server.ssrLoadModule('/src/lib/format.ts'),
    server.ssrLoadModule('/src/lib/money.ts'),
    server.ssrLoadModule('/src/services/api/apiClient.ts'),
    server.ssrLoadModule('/src/services/api/transactionOutcome.ts'),
    server.ssrLoadModule('/src/services/api/pendingTransactionOperation.ts'),
    server.ssrLoadModule('/src/services/api/authApi.ts'),
    server.ssrLoadModule('/src/services/api/accountsApi.ts'),
    server.ssrLoadModule('/src/services/api/categoriesApi.ts'),
    server.ssrLoadModule('/src/App.tsx'),
    server.ssrLoadModule('/src/hooks/authContext.ts'),
    server.ssrLoadModule('/src/pages/AuthPage.tsx'),
    server.ssrLoadModule('/src/services/mockFinanceSession.ts'),
    server.ssrLoadModule('/src/hooks/authOperationGuard.ts'),
    server.ssrLoadModule('/src/hooks/AuthProvider.tsx'),
    server.ssrLoadModule('/src/hooks/AccountCategoryProvider.tsx'),
    server.ssrLoadModule('/src/hooks/accountCategoryContext.ts'),
    server.ssrLoadModule('/src/pages/SettingsPage.tsx'),
    server.ssrLoadModule('/src/hooks/financeContext.ts'),
    server.ssrLoadModule('/src/services/api/transactionsApi.ts'),
    server.ssrLoadModule('/src/hooks/TransactionsProvider.tsx'),
    server.ssrLoadModule('/src/hooks/transactionsContext.ts'),
    server.ssrLoadModule('/src/pages/TransactionsPage.tsx'),
    server.ssrLoadModule('/src/components/transactions/TransactionDialog.tsx'),
    server.ssrLoadModule('/src/components/ui/dialog.tsx'),
    server.ssrLoadModule('/src/services/api/dashboardApi.ts'),
    server.ssrLoadModule('/src/hooks/dashboardContext.ts'),
    server.ssrLoadModule('/src/hooks/DashboardProvider.tsx'),
    server.ssrLoadModule('/src/pages/DashboardPage.tsx'),
  ])
  MockFinanceRepository = repositoryModule.MockFinanceRepository
  MockAssistantService = assistantModule.MockAssistantService
  calculations = calculationModule
  getCurrentMonthKey = formatModule.getCurrentMonthKey
  getTodayDateKey = formatModule.getTodayDateKey
  getIndiaMonthKey = formatModule.getIndiaMonthKey
  getIndiaMonthStart = formatModule.getIndiaMonthStart
  getMonthStartDateKey = formatModule.getMonthStartDateKey
  formatDate = formatModule.formatDate
  isValidDateKey = formatModule.isValidDateKey
  parseAmountToPaise = moneyModule.parseAmountToPaise
  ApiClient = apiModule.ApiClient
  classifyTransactionCreateOutcome = outcomeModule.classifyTransactionCreateOutcome
  readPendingTransactionOperation = pendingOperationModule.readPendingTransactionOperation
  storePendingTransactionOperation = pendingOperationModule.storePendingTransactionOperation
  abandonInvalidPendingTransactionOperation = pendingOperationModule.abandonInvalidPendingTransactionOperation
  ApiError = apiModule.ApiError
  ApiNetworkError = apiModule.ApiNetworkError
  ApiCsrfError = apiModule.ApiCsrfError
  ApiContractError = apiModule.ApiContractError
  ApiUrlError = apiModule.ApiUrlError
  getApiBaseUrl = apiModule.getApiBaseUrl
  AuthApi = authModule.AuthApi
  AuthFinalizationError = authModule.AuthFinalizationError
  AccountsApi = accountsModule.AccountsApi
  CategoriesApi = categoriesModule.CategoriesApi
  App = appModule.default
  AuthContext = authContextModule.AuthContext
  AuthPage = authPageModule.AuthPage
  getMockFinanceSessionServices = mockSessionModule.getMockFinanceSessionServices
  AuthOperationGuard = authGuardModule.AuthOperationGuard
  AuthProvider = authProviderModule.AuthProvider
  useAuth = authContextModule.useAuth
  SessionGate = appModule.SessionGate
  AccountCategoryProvider = accountCategoryProviderModule.AccountCategoryProvider
  AccountCategoryContext = accountCategoryContextModule.AccountCategoryContext
  useAccountCategoryData = accountCategoryContextModule.useAccountCategoryData
  SettingsPage = settingsModule.SettingsPage
  FinanceContext = financeContextModule.FinanceContext
  TransactionsApi = transactionsApiModule.TransactionsApi
  parseTransactionDto = (await server.ssrLoadModule('/src/services/api/responseSchemas.ts')).parseTransactionDto
  createTransactionOperationKey = transactionsApiModule.createTransactionOperationKey
  TransactionsProvider = transactionsProviderModule.TransactionsProvider
  TransactionsContext = transactionsContextModule.TransactionsContext
  useTransactions = transactionsContextModule.useTransactions
  TransactionsPage = transactionsPageModule.TransactionsPage
  TransactionForm = transactionDialogModule.TransactionForm
  Dialog = dialogModule.Dialog
  DashboardApi = dashboardApiModule.DashboardApi
  DashboardContext = dashboardContextModule.DashboardContext
  DashboardProvider = dashboardProviderModule.DashboardProvider
  DashboardPage = dashboardPageModule.DashboardPage
  const budgetGoalSchemaModule = await server.ssrLoadModule('/src/services/api/responseSchemas.ts')
  const formatExactModule = await server.ssrLoadModule('/src/lib/format.ts')
  const [budgetsApiModule, goalsApiModule] = await Promise.all([
    server.ssrLoadModule('/src/services/api/budgetsApi.ts'),
    server.ssrLoadModule('/src/services/api/goalsApi.ts'),
  ])
  parseBudgetDto = budgetGoalSchemaModule.parseBudgetDto
  parseBudgetListDto = budgetGoalSchemaModule.parseBudgetListDto
  parseGoalDto = budgetGoalSchemaModule.parseGoalDto
  parseGoalListDto = budgetGoalSchemaModule.parseGoalListDto
  parseGoalEntryListDto = budgetGoalSchemaModule.parseGoalEntryListDto
  parseDashboardSummaryDto = budgetGoalSchemaModule.parseDashboardSummaryDto
  formatPaiseExact = formatExactModule.formatPaiseExact
  formatBasisPoints = formatExactModule.formatBasisPoints
  BudgetsApi = budgetsApiModule.BudgetsApi
  GoalsApi = goalsApiModule.GoalsApi
  const [budgetProviderModule, budgetContextModule, goalsProviderModule, goalsContextModule, accountCategoryContextForGoalsModule] = await Promise.all([
    server.ssrLoadModule('/src/hooks/BudgetsProvider.tsx'),
    server.ssrLoadModule('/src/hooks/budgetsContext.ts'),
    server.ssrLoadModule('/src/hooks/SavingsGoalsProvider.tsx'),
    server.ssrLoadModule('/src/hooks/savingsGoalsContext.ts'),
    server.ssrLoadModule('/src/hooks/accountCategoryContext.ts'),
  ])
  BudgetsProvider = budgetProviderModule.BudgetsProvider
  BudgetsContext = budgetContextModule.BudgetsContext
  SavingsGoalsProvider = goalsProviderModule.SavingsGoalsProvider
  SavingsGoalsContext = goalsContextModule.SavingsGoalsContext
  AccountCategoryContextForGoals = accountCategoryContextForGoalsModule.AccountCategoryContext
  GoalMoneyDialog = (await server.ssrLoadModule('/src/components/goals/GoalDialogs.tsx')).GoalMoneyDialog
})

after(async () => {
  await server?.close()
  moduleDom?.window.close()
  for (const [name, descriptor] of moduleGlobals ?? []) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor)
    else delete globalThis[name]
  }
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

test('mock finance and assistant services are isolated and stable within auth-session generations', async () => {
  const identityA = { generation: 1 }
  const sessionA = getMockFinanceSessionServices(identityA)
  await sessionA.repository.addTransaction(currentDraft({
    description: 'Session A private sample',
    amountPaise: 100000000,
    category: 'Food & dining',
  }))
  await sessionA.repository.addBudget({ category: 'Education', limitPaise: 80000, month: '2099-01' })
  await sessionA.repository.addGoal({ name: 'Session A goal', targetPaise: 200000, targetDate: '2030-01-01' })

  const sameSessionRerender = getMockFinanceSessionServices(identityA)
  assert.strictEqual(sameSessionRerender.repository, sessionA.repository)
  assert.strictEqual(sameSessionRerender.assistantService, sessionA.assistantService)
  assert.ok(sameSessionRerender.repository.getSnapshot().transactions.some((item) => item.description === 'Session A private sample'))

  const sessionAReply = await sessionA.assistantService.reply('where did my money go this month?')
  const sessionB = getMockFinanceSessionServices({ generation: 2 })
  assert.notStrictEqual(sessionB.repository, sessionA.repository)
  assert.notStrictEqual(sessionB.assistantService, sessionA.assistantService)
  assert.equal(sessionB.repository.getSnapshot().transactions.some((item) => item.description === 'Session A private sample'), false)
  assert.equal(sessionB.repository.getSnapshot().budgets.some((item) => item.month === '2099-01'), false)
  assert.equal(sessionB.repository.getSnapshot().goals.some((item) => item.name === 'Session A goal'), false)
  assert.notEqual(await sessionB.assistantService.reply('where did my money go this month?'), sessionAReply)

  // New generations represent logout/login for the same user and user switching alike.
  const sameUserAfterLogoutLogin = getMockFinanceSessionServices({ generation: 3 })
  const differentUser = getMockFinanceSessionServices({ generation: 4 })
  assert.equal(sameUserAfterLogoutLogin.repository.getSnapshot().transactions.some((item) => item.description === 'Session A private sample'), false)
  assert.equal(differentUser.repository.getSnapshot().transactions.some((item) => item.description === 'Session A private sample'), false)
  assert.notStrictEqual(sameUserAfterLogoutLogin.repository, sessionB.repository)
  assert.notStrictEqual(differentUser.repository, sameUserAfterLogoutLogin.repository)
})

test('auth operation guard ignores session-restoration completion after provider unmount', async () => {
  let resolveRestore
  const pendingRestore = new Promise((resolve) => { resolveRestore = resolve })
  const guard = new AuthOperationGuard()
  guard.activate()
  const generation = guard.begin()
  const updates = []
  const completion = pendingRestore.then((user) => {
    if (guard.isCurrent(generation)) updates.push(user)
  })

  guard.invalidate()
  resolveRestore({ id: 'user' })
  await completion
  assert.deepEqual(updates, [])
})

test('auth operation guard handles StrictMode effect cleanup and replay', async () => {
  const guard = new AuthOperationGuard()
  guard.activate()
  const firstEffect = guard.begin()
  guard.invalidate()
  guard.activate()
  const replayedEffect = guard.begin()
  assert.equal(guard.isCurrent(firstEffect), false)
  assert.equal(guard.isCurrent(replayedEffect), true)
})

test('auth operation guard ignores a login completion after provider unmount', async () => {
  let resolveLogin
  const pendingLogin = new Promise((resolve) => { resolveLogin = resolve })
  const guard = new AuthOperationGuard()
  guard.activate()
  const loginGeneration = guard.begin()
  const updates = []
  const completion = pendingLogin.then((user) => {
    if (guard.isCurrent(loginGeneration)) updates.push(user)
  })

  guard.invalidate()
  resolveLogin({ id: 'stale-user' })
  await completion
  assert.equal(guard.isCurrent(loginGeneration), false)
  assert.deepEqual(updates, [])
})

test('auth operation guard prevents an older request overwriting a newer auth action', async () => {
  const guard = new AuthOperationGuard()
  guard.activate()
  const oldRequest = guard.begin()
  const newRequest = guard.begin()
  assert.equal(guard.isCurrent(oldRequest), false)
  assert.equal(guard.isCurrent(newRequest), true)
  guard.invalidate()
  assert.equal(guard.isCurrent(newRequest), false)
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

test('transaction amount input converts decimal INR to exact paise without rounding', () => {
  assert.equal(parseAmountToPaise('12'), 1200)
  assert.equal(parseAmountToPaise('12.3'), 1230)
  assert.equal(parseAmountToPaise('12.34'), 1234)
  assert.equal(parseAmountToPaise('0.01'), 1)
  assert.equal(parseAmountToPaise('90071992547409.91'), Number.MAX_SAFE_INTEGER)
  assert.equal(parseAmountToPaise('90071992547409.92'), null)
  for (const invalidAmount of ['', '0', '0.00', '-1.00', '1.001', '1e2', '90071992547409.92']) {
    assert.equal(parseAmountToPaise(invalidAmount), null, `${invalidAmount} should be rejected`)
  }
})

test('financial date key uses India time around midnight regardless of device timezone', () => {
  const previousTimezone = process.env.TZ
  process.env.TZ = 'Pacific/Honolulu'
  try {
    const beforeIndiaMidnight = new Date('2026-11-13T18:29:59.000Z')
    const atIndiaMidnight = new Date('2026-11-13T18:30:00.000Z')
    assert.equal(beforeIndiaMidnight.getDate(), 13)
    assert.equal(atIndiaMidnight.getDate(), 13)
    assert.equal(getTodayDateKey(beforeIndiaMidnight), '2026-11-13')
    assert.equal(getTodayDateKey(atIndiaMidnight), '2026-11-14')
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ
    else process.env.TZ = previousTimezone
  }
})

test('date-only validation is timezone-independent and checks leap and impossible calendar dates', () => {
  const previousTimezone = process.env.TZ
  process.env.TZ = 'Pacific/Apia'
  try {
    assert.equal(isValidDateKey('2011-12-30'), true)
    assert.match(formatDate('2011-12-30'), /30 Dec 2011/)
    assert.match(formatDate('2024-02-29'), /29 Feb 2024/)
    assert.match(formatDate('2026-01-01'), /1 Jan 2026/)
    assert.match(formatDate('2025-12-31'), /31 Dec 2025/)
    assert.equal(isValidDateKey('2024-02-29'), true)
    assert.equal(isValidDateKey('0001-01-01'), true)
    assert.equal(isValidDateKey('9999-12-31'), true)
    assert.equal(isValidDateKey('0000-01-01'), false)
    assert.equal(isValidDateKey('2023-02-29'), false)
    assert.equal(isValidDateKey('2026-04-31'), false)
    assert.equal(isValidDateKey('not-a-date'), false)
    assert.equal(formatDate('2026-02-30'), '2026-02-30')
    assert.equal(isValidDateKey('2026-11-13'), true)
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ
    else process.env.TZ = previousTimezone
  }
})

test('transaction create outcome classification preserves uncertain transport and unexpected statuses', () => {
  assert.equal(classifyTransactionCreateOutcome(new ApiError(404, 'Account not found')), 'definitive-rejection')
  assert.equal(classifyTransactionCreateOutcome(new ApiError(404, 'Not found')), 'uncertain')
  assert.equal(classifyTransactionCreateOutcome(new ApiError(422, 'Invalid transaction')), 'definitive-rejection')
  assert.equal(classifyTransactionCreateOutcome(new ApiError(409, 'Key conflict')), 'idempotency-conflict')
  assert.equal(classifyTransactionCreateOutcome(new ApiError(401, 'Sign in')), 'unauthorized')
  for (const status of [408, 400, 403, 418, 429, 500, 502, 504]) {
    assert.equal(classifyTransactionCreateOutcome(new ApiError(status, 'Request failed')), 'uncertain', `HTTP ${status}`)
  }
  assert.equal(classifyTransactionCreateOutcome(new ApiNetworkError()), 'uncertain')
  assert.equal(classifyTransactionCreateOutcome(new Error('unknown failure')), 'uncertain')
})

test('pending operation storage distinguishes corrupt, incomplete, invalid and unsupported markers', () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const key = `vibewealth:pending-transaction:v1:${userId}`
  const storage = moduleDom.window.sessionStorage
  for (const serialized of ['{bad json', '{}', JSON.stringify({ version: 1, userId }), JSON.stringify({ version: 1, userId, key: 'short' })]) {
    storage.setItem(key, serialized)
    const result = readPendingTransactionOperation(userId)
    assert.equal(result.status, 'invalid')
    assert.equal(result.recoverableKey, null)
  }
  storage.setItem(key, JSON.stringify({ version: 2, userId, key: 'future-operation-key-0001' }))
  assert.deepEqual(readPendingTransactionOperation(userId), { status: 'invalid', recoverableKey: 'future-operation-key-0001', reason: 'unsupported' })
  assert.equal(readPendingTransactionOperation('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb').status, 'empty')
  assert.notEqual(storage.getItem(key), null)
  abandonInvalidPendingTransactionOperation(userId)
  assert.equal(storage.getItem(key), null)
})

test('pending operation storage reports read and write failures without replacing the marker', () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const browserWindow = moduleDom.window
  const storageDescriptor = Object.getOwnPropertyDescriptor(browserWindow, 'sessionStorage')
  const storage = browserWindow.sessionStorage
  try {
    Object.defineProperty(browserWindow, 'sessionStorage', {
      configurable: true,
      value: {
        getItem() { throw new Error('blocked') },
        setItem: (...args) => storage.setItem(...args),
        removeItem: (...args) => storage.removeItem(...args),
      },
    })
    assert.throws(() => readPendingTransactionOperation(userId), /storage is unavailable/i)
  } finally {
    Object.defineProperty(browserWindow, 'sessionStorage', storageDescriptor)
  }
  const storageKey = `vibewealth:pending-transaction:v1:${userId}`
  storage.setItem(storageKey, JSON.stringify({ version: 1, userId, key: 'existing-operation-key-001' }))
  try {
    Object.defineProperty(browserWindow, 'sessionStorage', {
      configurable: true,
      value: {
        getItem: (...args) => storage.getItem(...args),
        setItem() { throw new Error('blocked') },
        removeItem: (...args) => storage.removeItem(...args),
      },
    })
    assert.throws(() => storePendingTransactionOperation({ version: 1, userId, key: 'existing-operation-key-001' }), /storage is unavailable/i)
  } finally {
    Object.defineProperty(browserWindow, 'sessionStorage', storageDescriptor)
  }
  assert.equal(readPendingTransactionOperation(userId).operation.key, 'existing-operation-key-001')
  storage.removeItem(storageKey)
})

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function scriptedAuthApi(responses) {
  const calls = []
  const queues = new Map(Object.entries(responses).map(([key, steps]) => [key, [...steps]]))
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    const parsedUrl = new URL(String(url))
    const key = `${options.method} ${parsedUrl.pathname}`
    calls.push({ key, url: parsedUrl.href, options })
    const step = queues.get(key)?.shift()
    if (step === undefined) throw new Error(`Unexpected request: ${key}`)
    if (step instanceof Error) throw step
    if (step instanceof Response) return step
    return jsonResponse(step.body ?? {}, step.status ?? 200)
  })
  return { service: new AuthApi(client), client, calls }
}

const validAuthUser = {
  id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  email: 'person@example.test',
  display_name: 'Person',
}

// Native browser fetch rejects an ApiClient instance as its receiver. Arrow
// mocks (and Node's fetch) do not exercise that browser-only invocation rule.
function browserAuthApi(responses) {
  const calls = []
  const queues = new Map(Object.entries(responses).map(([key, steps]) => [key, [...steps]]))
  const previousFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    writable: true,
    value: async function (url, options) {
      if (this !== globalThis) throw new TypeError('Illegal invocation')
      const parsedUrl = new URL(String(url))
      const key = `${options.method} ${parsedUrl.pathname}`
      calls.push({ key, url: parsedUrl.href, options })
      const step = queues.get(key)?.shift()
      assert.notEqual(step, undefined, `Unexpected request: ${key}`)
      if (step instanceof Error) throw step
      return jsonResponse(step.body ?? {}, step.status ?? 200)
    },
  })
  let client
  try {
    client = new ApiClient() // Exercise default fetch capture and API base URL.
  } finally {
    Object.defineProperty(globalThis, 'fetch', previousFetch)
  }
  return { service: new AuthApi(client), client, calls }
}

test('default browser fetch restores the mounted StrictMode session with one shared request', async () => {
  const { service, client, calls } = browserAuthApi({
    'GET /api/auth/me': [{ body: validAuthUser }],
    'GET /api/auth/csrf': [{ body: { csrf_token: 'restored-csrf' } }],
    'POST /api/auth/logout': [{ body: {} }],
  })
  let restores = 0
  const restoreSession = service.restoreSession.bind(service)
  service.restoreSession = () => { restores += 1; return restoreSession() }
  const mounted = await mountAuthProvider(service)
  try {
    assert.equal(restores, 2, 'StrictMode replays the restoration effect')
    assert.equal(mounted.status, 'authenticated')
    assert.deepEqual(mounted.auth.user, validAuthUser)
    assert.ok(mounted.auth.sessionIdentity)
    assert.deepEqual(calls.map((call) => call.url), [
      'http://localhost:8000/api/auth/me', 'http://localhost:8000/api/auth/csrf',
    ])
    assert.ok(calls.every((call) => call.options.credentials === 'include'))
    assert.ok(calls.every((call) => call.options.redirect === 'error'))
    assert.ok(calls.every((call) => !call.options.headers.has('X-CSRF-Token')))
    assert.equal(client.hasCsrfToken(), true)
    await act(async () => mounted.auth.logout())
    assert.equal(calls.at(-1).options.headers.get('X-CSRF-Token'), 'restored-csrf')
    assert.equal(mounted.status, 'unauthenticated')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

for (const failurePath of ['me', 'csrf']) {
  test(`mounted browser restoration retries a network failure at /${failurePath} with fresh requests`, async () => {
    const { service, calls } = browserAuthApi({
      'GET /api/auth/me': failurePath === 'me'
        ? [new TypeError('offline'), { body: validAuthUser }]
        : [{ body: validAuthUser }, { body: validAuthUser }],
      'GET /api/auth/csrf': failurePath === 'csrf'
        ? [new TypeError('offline'), { body: { csrf_token: 'retry-csrf' } }]
        : [{ body: { csrf_token: 'retry-csrf' } }],
    })
    const mounted = await mountAuthProvider(service)
    try {
      assert.equal(mounted.status, 'restore-error')
      assert.match(mounted.text, /Unable to reach VibeWealth/)
      assert.equal(calls.filter((call) => call.key === 'GET /api/auth/me').length, 1)
      await act(async () => mounted.auth.retrySessionRestore())
      assert.equal(mounted.status, 'authenticated')
      assert.deepEqual(mounted.auth.user, validAuthUser)
      assert.equal(mounted.auth.authError, null)
      assert.deepEqual(calls.map((call) => call.key), failurePath === 'me'
        ? ['GET /api/auth/me', 'GET /api/auth/me', 'GET /api/auth/csrf']
        : ['GET /api/auth/me', 'GET /api/auth/csrf', 'GET /api/auth/me', 'GET /api/auth/csrf'])
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  })

  test(`mounted browser restoration treats /${failurePath} HTTP 401 as unauthenticated`, async () => {
    const { service, client, calls } = browserAuthApi({
      'GET /api/auth/me': [failurePath === 'me' ? { status: 401 } : { body: validAuthUser }],
      'GET /api/auth/csrf': [{ status: 401 }],
    })
    client.setCsrfToken('old-token')
    const mounted = await mountAuthProvider(service)
    try {
      assert.equal(mounted.status, 'unauthenticated')
      assert.equal(mounted.auth.user, null)
      assert.equal(mounted.auth.authError, null)
      assert.equal(client.hasCsrfToken(), false)
      assert.deepEqual(calls.map((call) => call.key), failurePath === 'me'
        ? ['GET /api/auth/me'] : ['GET /api/auth/me', 'GET /api/auth/csrf'])
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  })

  test(`concurrent browser restoration releases a rejected /${failurePath} promise before retry`, async () => {
    const { service, calls } = browserAuthApi({
      'GET /api/auth/me': failurePath === 'me'
        ? [new TypeError('offline'), { body: validAuthUser }]
        : [{ body: validAuthUser }, { body: validAuthUser }],
      'GET /api/auth/csrf': failurePath === 'csrf'
        ? [new TypeError('offline'), { body: { csrf_token: 'retry-csrf' } }]
        : [{ body: { csrf_token: 'retry-csrf' } }],
    })
    const first = service.restoreSession()
    assert.strictEqual(service.restoreSession(), first)
    const results = await Promise.allSettled([first, service.restoreSession()])
    assert.ok(results.every((result) => result.status === 'rejected' && result.reason instanceof ApiNetworkError))
    const retry = service.restoreSession()
    assert.notStrictEqual(retry, first)
    assert.strictEqual(service.restoreSession(), retry)
    assert.deepEqual(await retry, validAuthUser)
    assert.equal(calls.filter((call) => call.key === 'GET /api/auth/me').length, 2)
    assert.equal(calls.filter((call) => call.key === 'GET /api/auth/csrf').length, failurePath === 'csrf' ? 2 : 1)
  })
}

async function startSignedOutProvider(service) {
  const mounted = await mountAuthProvider(service)
  await mounted.flush()
  assert.equal(mounted.status, 'unauthenticated')
  return mounted
}

async function mountAuthProvider(service, onAuth = (auth) => auth, children = null) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement,
    Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }

  try {
    const { createRoot } = await import('react-dom/client')
    const container = dom.window.document.getElementById('root')
    const root = createRoot(container)
    let currentAuth
    function Probe() {
      currentAuth = onAuth(useAuth())
      return createElement('div', null,
        createElement('output', { 'data-status': currentAuth.status }, currentAuth.authError ?? ''),
        children,
      )
    }
    await act(async () => {
      root.render(createElement(
        StrictMode,
        null,
        createElement(AuthProvider, { service }, createElement(Probe)),
      ))
    })
    return {
      get auth() { return currentAuth },
      get text() { return container.textContent },
      get status() { return container.querySelector('output')?.getAttribute('data-status') },
      async flush() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) }) },
      async unmount() { await act(async () => root.unmount()) },
      close() {
        dom.window.close()
        for (const [name, descriptor] of previousGlobals) {
          if (descriptor) Object.defineProperty(globalThis, name, descriptor)
          else delete globalThis[name]
        }
      },
    }
  } catch (error) {
    dom.window.close()
    for (const [name, descriptor] of previousGlobals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
    throw error
  }
}

function validAccountDto(overrides = {}) {
  return {
    id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    name: 'Primary account',
    account_type: 'bank',
    is_default: true,
    opening_balance_paise: 4500,
    opening_balance_as_of: '2026-01-01',
    balance_paise: 9007199254740991,
    goal_allocated_paise: 1250,
    available_to_spend_paise: 9007199254739741,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function validCategoryDto(overrides = {}) {
  return {
    id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    name: 'Salary',
    transaction_type: 'income',
    ...overrides,
  }
}

async function mountAccountCategoryProvider(props) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement,
    Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }

  try {
    const { createRoot } = await import('react-dom/client')
    const container = dom.window.document.getElementById('root')
    const root = createRoot(container)
    let currentData
    function Probe() {
      currentData = useAccountCategoryData()
      return createElement('output', {
        'data-account-status': currentData.accounts.status,
        'data-category-status': currentData.categories.status,
      })
    }
    const render = (nextProps) => root.render(createElement(
      StrictMode,
      null,
      createElement(AccountCategoryProvider, {
        ...nextProps,
        key: nextProps.sessionIdentity.generation,
      }, createElement(Probe)),
    ))
    await act(async () => render(props))
    return {
      get data() { return currentData },
      get accountStatus() { return container.querySelector('output')?.getAttribute('data-account-status') },
      get categoryStatus() { return container.querySelector('output')?.getAttribute('data-category-status') },
      async rerender(nextProps) { await act(async () => render(nextProps)) },
      async flush() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) }) },
      async unmount() { await act(async () => root.unmount()) },
      close() {
        dom.window.close()
        for (const [name, descriptor] of previousGlobals) {
          if (descriptor) Object.defineProperty(globalThis, name, descriptor)
          else delete globalThis[name]
        }
      },
    }
  } catch (error) {
    dom.window.close()
    for (const [name, descriptor] of previousGlobals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
    throw error
  }
}

async function mountTransactionsProvider(service, { sessionGeneration = 1, userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', retryAccounts = async () => {}, onUnauthorized = async () => {}, accountServices = null, pendingRecord = null } = {}) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement,
    Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }

  try {
    const { createRoot } = await import('react-dom/client')
    const container = dom.window.document.getElementById('root')
    const root = createRoot(container)
    if (pendingRecord !== null) {
      dom.window.sessionStorage.setItem(`vibewealth:pending-transaction:v1:${userId}`, JSON.stringify(pendingRecord))
    }
    let currentTransactions
    let currentAccountData
    function Probe() {
      currentTransactions = useTransactions()
      currentAccountData = useAccountCategoryData()
      return createElement('output', {
        'data-list-status': currentTransactions.list.status,
        'data-is-creating': String(currentTransactions.isCreating),
        'data-account-status': currentAccountData.accounts.status,
        'data-account-error': currentAccountData.accounts.error ?? '',
        'data-recovery-status': currentTransactions.recovery.status,
      })
    }
    const render = (generation, currentUserId = userId) => {
      const transactionsTree = createElement(TransactionsProvider, {
        key: generation,
        sessionGeneration: generation,
        userId: currentUserId,
        service,
        onUnauthorized,
      }, createElement(Probe))
      const accountTree = accountServices
        ? createElement(AccountCategoryProvider, {
          key: generation,
          sessionIdentity: { generation },
          onUnauthorized,
          accountsService: accountServices.accounts,
          categoriesService: accountServices.categories,
        }, transactionsTree)
        : createElement(AccountCategoryContext.Provider, {
        value: {
          accounts: { status: 'success', data: [validAccountDto()], error: null },
          categories: { status: 'success', data: [validCategoryDto({ transaction_type: 'expense' }), validCategoryDto({ id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', name: 'Salary', transaction_type: 'income' })], error: null },
          retryAccounts,
          retryCategories: async () => {},
        },
      }, transactionsTree)
      root.render(createElement(StrictMode, null, accountTree))
    }
    await act(async () => render(sessionGeneration))
    return {
      get transactions() { return currentTransactions },
      get status() { return container.querySelector('output')?.getAttribute('data-list-status') },
      get isCreating() { return container.querySelector('output')?.getAttribute('data-is-creating') === 'true' },
      get accountStatus() { return container.querySelector('output')?.getAttribute('data-account-status') },
      get accountError() { return container.querySelector('output')?.getAttribute('data-account-error') },
      get recoveryStatus() { return container.querySelector('output')?.getAttribute('data-recovery-status') },
      storage: dom.window.sessionStorage,
      retryAccounts,
      async retryAccountData() { await act(async () => currentAccountData.retryAccounts()) },
      async rerender(generation, currentUserId = userId) { await act(async () => render(generation, currentUserId)) },
      async flush() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) }) },
      async unmount() { await act(async () => root.unmount()) },
      close() {
        dom.window.close()
        for (const [name, descriptor] of previousGlobals) {
          if (descriptor) Object.defineProperty(globalThis, name, descriptor)
          else delete globalThis[name]
        }
      },
    }
  } catch (error) {
    dom.window.close()
    for (const [name, descriptor] of previousGlobals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
    throw error
  }
}

async function mountTransactionForm(onSave, { recoveryOperationKey = null } = {}) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT', 'requestAnimationFrame', 'cancelAnimationFrame']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement,
    Element: dom.window.Element,
    Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver,
    IS_REACT_ACT_ENVIRONMENT: true,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
  })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }

  try {
    const { createRoot } = await import('react-dom/client')
    const container = dom.window.document.getElementById('root')
    const root = createRoot(container)
    await act(async () => root.render(createElement(Dialog, { open: true }, createElement(
      AccountCategoryContext.Provider,
      { value: {
        accounts: { status: 'success', data: [validAccountDto()], error: null },
        categories: { status: 'success', data: [
          validCategoryDto({ transaction_type: 'expense' }),
          validCategoryDto({ id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', name: 'Salary', transaction_type: 'income' }),
        ], error: null },
        retryAccounts: async () => {},
        retryCategories: async () => {},
      } },
      createElement(TransactionForm, { onCancel() {}, onSave, isSaving: false, recoveryOperationKey }),
    ))))
    return {
      document: dom.window.document,
      async setInput(id, value) {
        const input = dom.window.document.querySelector(`#${id}`)
        const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set
        setter.call(input, value)
        await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })))
      },
      async submit() {
        const form = dom.window.document.querySelector('form')
        await act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
      },
      async unmount() { await act(async () => root.unmount()) },
      close() {
        dom.window.close()
        for (const [name, descriptor] of previousGlobals) {
          if (descriptor) Object.defineProperty(globalThis, name, descriptor)
          else delete globalThis[name]
        }
      },
    }
  } catch (error) {
    dom.window.close()
    for (const [name, descriptor] of previousGlobals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
    throw error
  }
}

async function mountTransactionsPage({ service, accountsService, categoriesService, pendingRecord = null }) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT', 'requestAnimationFrame', 'cancelAnimationFrame']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement,
    Element: dom.window.Element,
    Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver,
    IS_REACT_ACT_ENVIRONMENT: true,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
  })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }

  try {
    const { createRoot } = await import('react-dom/client')
    const container = dom.window.document.getElementById('root')
    const root = createRoot(container)
    if (pendingRecord !== null) dom.window.sessionStorage.setItem('vibewealth:pending-transaction:v1:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', typeof pendingRecord === 'string' ? pendingRecord : JSON.stringify(pendingRecord))
    const financeValue = { preferences: { currency: 'INR' } }
    const accountTree = createElement(AccountCategoryProvider, {
      sessionIdentity: { generation: 31 },
      onUnauthorized: async () => {},
      accountsService,
      categoriesService,
    }, createElement(TransactionsProvider, {
      sessionGeneration: 31,
      userId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      onUnauthorized: async () => {},
      service,
    }, createElement(TransactionsPage)))
    await act(async () => root.render(createElement(
      FinanceContext.Provider,
      { value: financeValue },
      accountTree,
    )))
    return {
      document: dom.window.document,
      window: dom.window,
      storage: dom.window.sessionStorage,
      async flush() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 10)) }) },
      async clickButton(label) {
        const button = [...dom.window.document.querySelectorAll('button')]
          .find((item) => item.textContent.trim().includes(label) && !item.disabled)
        assert.ok(button, `Expected button containing ${label}`)
        await act(async () => button.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true, cancelable: true })))
      },
      async setInput(id, value) {
        const input = dom.window.document.querySelector(`#${id}`)
        assert.ok(input, `Expected input #${id}`)
        const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set
        setter.call(input, value)
        await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })))
      },
      async submit() {
        const form = dom.window.document.querySelector('form')
        assert.ok(form)
        await act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
      },
      async unmount() { await act(async () => root.unmount()) },
      close() {
        dom.window.close()
        for (const [name, descriptor] of previousGlobals) {
          if (descriptor) Object.defineProperty(globalThis, name, descriptor)
          else delete globalThis[name]
        }
      },
    }
  } catch (error) {
    dom.window.close()
    for (const [name, descriptor] of previousGlobals) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
    throw error
  }
}

function validTransactionDto(overrides = {}) {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    account_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    category_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    category_name: 'Food',
    transaction_type: 'expense',
    amount_paise: 4295,
    description: 'Lunch',
    transaction_date: '2026-01-02',
    notes: null,
    created_at: '2026-01-02T10:30:00Z',
    updated_at: '2026-01-02T10:30:00Z',
    ...overrides,
  }
}

function validTransactionPage(items = [validTransactionDto()], overrides = {}) {
  return { items, total: items.length, offset: 0, limit: 50, ...overrides }
}

test('transaction API uses the backend list filters, pagination, credentials, and validates the response', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: new URL(String(url)), options })
    return jsonResponse(validTransactionPage())
  })
  const api = new TransactionsApi(client)
  const result = await api.list({
    account_id: validAccountDto().id,
    transaction_type: 'expense',
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    date_from: '2026-01-01',
    date_to: '2026-01-31',
    offset: 25,
    limit: 25,
  })

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url.pathname, '/api/transactions')
  assert.deepEqual(Object.fromEntries(calls[0].url.searchParams), {
    account_id: validAccountDto().id,
    transaction_type: 'expense',
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    date_from: '2026-01-01',
    date_to: '2026-01-31',
    offset: '25',
    limit: '25',
  })
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(result.items[0].amount_paise, 4295)
  assert.equal(result.total, 1)
})

test('transaction API creates with CSRF and rejects malformed transaction and pagination DTOs', async () => {
  let receivedBody
  let receivedCsrf
  let receivedIdempotencyKey
  let receivedOptions
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    assert.equal(new URL(String(url)).pathname, '/api/transactions')
    receivedOptions = options
    receivedBody = JSON.parse(options.body)
    receivedCsrf = options.headers.get('X-CSRF-Token')
    receivedIdempotencyKey = options.headers.get('Idempotency-Key')
    return jsonResponse(validTransactionDto(), 201)
  })
  client.setCsrfToken('session-csrf')
  const api = new TransactionsApi(client)
  const input = {
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense',
    amount_paise: 4295,
    description: 'Lunch',
    transaction_date: '2026-01-02',
  }
  const operationKey = createTransactionOperationKey()
  assert.equal((await api.create(input, operationKey)).id, validTransactionDto().id)
  assert.equal(receivedOptions.method, 'POST')
  assert.equal(receivedOptions.credentials, 'include')
  assert.equal(receivedCsrf, 'session-csrf')
  assert.equal(receivedIdempotencyKey, operationKey)
  assert.deepEqual(receivedBody, input)

  for (const invalidDto of [
    validTransactionDto({ id: 'not-a-uuid' }),
    validTransactionDto({ category_id: 7 }),
    validTransactionDto({ category_name: 7 }),
    validTransactionDto({ transaction_type: 'transfer' }),
    validTransactionDto({ amount_paise: Number.MAX_SAFE_INTEGER + 1 }),
    validTransactionDto({ amount_paise: 0 }),
    validTransactionDto({ transaction_date: '2026-02-30' }),
    validTransactionDto({ notes: 7 }),
    validTransactionDto({ created_at: 'not-a-timestamp' }),
  ]) {
    const invalidClient = new ApiClient('http://localhost:8000', async () => jsonResponse(invalidDto))
    invalidClient.setCsrfToken('session-csrf')
    const invalidApi = new TransactionsApi(invalidClient)
    await assert.rejects(invalidApi.create(input), ApiContractError)
  }

  const malformedPageApi = new TransactionsApi(new ApiClient('http://localhost:8000', async () => jsonResponse({
    items: [validTransactionDto()], total: 1, offset: -1, limit: 50,
  })))
  await assert.rejects(malformedPageApi.list({ offset: 0, limit: 50 }), ApiContractError)
})

test('transaction DTO dates match Python date range and Gregorian calendar rules', () => {
  for (const date of ['0001-01-01', '9999-12-31', '2000-02-29', '2400-02-29', '2024-02-29']) {
    assert.equal(parseTransactionDto(validTransactionDto({ transaction_date: date })).transaction_date, date)
  }
  for (const date of [
    '0000-01-01',
    '1900-02-29',
    '2100-02-29',
    '2026-02-30',
    '2026-04-31',
    '2026-2-03',
    '2026-02-3',
    '2026/02/03',
    '2026-02-03T00:00:00Z',
  ]) {
    assert.throws(
      () => parseTransactionDto(validTransactionDto({ transaction_date: date })),
      ApiContractError,
      `Expected ${date} to be rejected`,
    )
  }
})

test('transaction operation resolution validates the response, includes cookies, and treats 404 as unresolved', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: new URL(String(url)), options })
    return jsonResponse(validTransactionDto())
  })
  const api = new TransactionsApi(client)
  const result = await api.resolveOperation('secure-operation-key-1234')
  assert.equal(result.id, validTransactionDto().id)
  assert.equal(calls[0].url.pathname, '/api/transactions/operations/secure-operation-key-1234')
  assert.equal(calls[0].options.method, 'GET')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false)

  const missingApi = new TransactionsApi(new ApiClient('http://localhost:8000', async () => jsonResponse({ detail: 'Operation not found' }, 404)))
  assert.equal(await missingApi.resolveOperation('secure-operation-key-1234'), null)
})

test('transaction API preserves a safe HTTP 401 error for the auth lifecycle', async () => {
  const api = new TransactionsApi(new ApiClient('http://localhost:8000', async () => jsonResponse({ detail: 'Authentication required' }, 401)))
  await assert.rejects(
    api.list({ offset: 0, limit: 50 }),
    (error) => error instanceof ApiError && error.status === 401,
  )
})

test('mounted transaction provider loads, retries, filters, creates, and refreshes account balances', async () => {
  const calls = []
  let listAttempt = 0
  const refreshes = []
  const service = {
    async list(query) {
      calls.push(query)
      listAttempt += 1
      if (listAttempt === 1) throw new ApiError(503, 'temporary list failure')
      return validTransactionPage([validTransactionDto()], { total: 51, offset: query.offset, limit: query.limit })
    },
    async create(input) {
      calls.push(input)
      return validTransactionDto({ account_id: input.account_id, category_id: input.category_id })
    },
  }
  const mounted = await mountTransactionsProvider(service, { retryAccounts: async () => refreshes.push('account') })
  try {
    await mounted.flush()
    assert.equal(mounted.status, 'error')
    await act(async () => mounted.transactions.retryList())
    assert.equal(mounted.status, 'success')
    await act(async () => mounted.transactions.setFilters({ transaction_type: 'expense', date_from: '2026-01-01' }))
    await mounted.flush()
    assert.equal(calls.at(-1).transaction_type, 'expense')
    assert.equal(calls.at(-1).date_from, '2026-01-01')
    assert.equal(calls.at(-1).offset, 0)
    await act(async () => mounted.transactions.setOffset(50))
    await mounted.flush()
    assert.equal(calls.at(-1).offset, 50)

    await act(async () => mounted.transactions.createTransaction({
      account_id: validAccountDto().id,
      category_id: validCategoryDto({ transaction_type: 'expense' }).id,
      transaction_type: 'expense',
      amount_paise: 4295,
      description: 'Lunch',
      transaction_date: '2026-01-02',
    }, 'test-operation-key-0001'))
    await mounted.flush()
    assert.equal(refreshes.length, 1)
    assert.equal(calls.at(-1).transaction_type, 'expense')
    assert.equal(calls.at(-1).date_from, '2026-01-01')
    assert.equal(calls.at(-1).offset, 50)
    assert.equal(mounted.isCreating, false)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('a successful transaction remains successful when list and account refreshes fail', async () => {
  let listCalls = 0
  let postCalls = 0
  let accountRefreshCalls = 0
  const service = {
    async list(query) {
      listCalls += 1
      if (listCalls === 2) throw new ApiError(503, 'list refresh failed')
      return validTransactionPage([validTransactionDto()], { offset: query.offset, limit: query.limit })
    },
    async create(input, key) {
      postCalls += 1
      assert.equal(key, 'committed-operation-key-0001')
      return validTransactionDto({ id: '22222222-2222-4222-8222-222222222222', description: input.description })
    },
  }
  const mounted = await mountTransactionsProvider(service, {
    retryAccounts: async () => {
      accountRefreshCalls += 1
      throw new ApiError(503, 'account refresh failed')
    },
  })
  const input = {
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense',
    amount_paise: 2500,
    description: 'Committed before refresh failure',
    transaction_date: '2026-01-02',
  }
  try {
    await mounted.flush()
    await act(async () => assert.doesNotReject(
      mounted.transactions.createTransaction(input, 'committed-operation-key-0001'),
    ))
    await mounted.flush()
    assert.equal(postCalls, 1)
    assert.equal(accountRefreshCalls, 1)
    assert.equal(mounted.status, 'error')

    await act(async () => mounted.transactions.retryList())
    await act(async () => assert.rejects(mounted.retryAccounts(), /account refresh failed/))
    assert.equal(accountRefreshCalls, 2)
    assert.equal(postCalls, 1)
    assert.equal(mounted.status, 'success')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('successful create survives a failed account refresh and account retry does not repost', async () => {
  let accountCalls = 0
  let postCalls = 0
  const account = validAccountDto()
  const mounted = await mountTransactionsProvider({
    async list(query) { return validTransactionPage([validTransactionDto()], { offset: query.offset, limit: query.limit }) },
    async create(input) {
      postCalls += 1
      return validTransactionDto({ description: input.description })
    },
  }, {
    accountServices: {
      accounts: { async list() {
        accountCalls += 1
        if (accountCalls === 2) throw new ApiError(503, 'Account refresh failed.')
        return [account]
      } },
      categories: { async listActive() { return [validCategoryDto({ transaction_type: 'expense' })] } },
    },
  })
  const input = {
    account_id: account.id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense',
    amount_paise: 1500,
    description: 'Create survives refresh error',
    transaction_date: '2026-01-02',
  }
  try {
    await mounted.flush()
    assert.equal(mounted.accountStatus, 'success')
    await act(async () => assert.doesNotReject(
      mounted.transactions.createTransaction(input, 'create-refresh-operation-0001'),
    ))
    await mounted.flush()
    assert.equal(postCalls, 1)
    assert.equal(mounted.accountStatus, 'error')
    assert.match(mounted.accountError, /Account refresh failed/)

    await mounted.retryAccountData()
    assert.equal(mounted.accountStatus, 'success')
    assert.equal(accountCalls, 3)
    assert.equal(postCalls, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted transactions page closes the dialog after create when list refresh fails', async () => {
  let listCalls = 0
  let postCalls = 0
  const transaction = validTransactionDto({ description: 'Saved before list refresh failure' })
  const mounted = await mountTransactionsPage({
    service: {
      async list(query) {
        listCalls += 1
        if (listCalls === 2) throw new ApiError(503, 'List refresh failed.')
        return listCalls === 1
          ? validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit })
          : validTransactionPage([transaction], { total: 1, offset: query.offset, limit: query.limit })
      },
      async create() { postCalls += 1; return transaction },
      async resolveOperation() { return null },
    },
    accountsService: { async list() { return [validAccountDto()] } },
    categoriesService: { async listActive() { return [validCategoryDto({ transaction_type: 'expense' })] } },
  })
  try {
    await mounted.flush()
    await mounted.clickButton('Add transaction')
    await mounted.flush()
    assert.ok(mounted.document.querySelector('#transaction-description'))
    await mounted.setInput('transaction-description', 'Saved before list refresh failure')
    await mounted.setInput('transaction-amount', '12.50')
    await mounted.submit()
    await mounted.flush()
    assert.equal(postCalls, 1)
    assert.equal(mounted.document.querySelector('#transaction-description'), null)
    assert.match(mounted.document.body.textContent, /Transaction saved to your account/)
    assert.match(mounted.document.body.textContent, /List refresh failed/)
    assert.ok([...mounted.document.querySelectorAll('button')].some((button) => button.textContent.includes('Retry transactions')))

    await mounted.clickButton('Retry transactions')
    await mounted.flush()
    assert.equal(postCalls, 1)
    assert.match(mounted.document.body.textContent, /Saved before list refresh failure/)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('successful creation refreshes after an in-flight list and ignores its stale result', async () => {
  let initialListStarted
  const initialStarted = new Promise((resolve) => { initialListStarted = resolve })
  let freshListStarted
  const freshStarted = new Promise((resolve) => { freshListStarted = resolve })
  let accountsStartedCallback
  const accountsStarted = new Promise((resolve) => { accountsStartedCallback = resolve })
  let categoriesStartedCallback
  const categoriesStarted = new Promise((resolve) => { categoriesStartedCallback = resolve })
  let resolveInitialList
  const initialList = new Promise((resolve) => { resolveInitialList = resolve })
  let resolveFreshList
  const freshList = new Promise((resolve) => { resolveFreshList = resolve })
  let listCalls = 0
  let postCalls = 0
  const transaction = validTransactionDto({
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    description: 'Freshly created transaction',
    amount_paise: 1250,
    transaction_date: '2026-11-13',
  })
  const mounted = await mountTransactionsPage({
    service: {
      list(query) {
        listCalls += 1
        if (listCalls === 1) {
          initialListStarted({ ...query })
          return initialList
        }
        if (listCalls === 2) {
          freshListStarted({ ...query })
          return freshList
        }
        assert.fail(`Unexpected additional transaction list request: ${JSON.stringify(query)}`)
      },
      async create() { postCalls += 1; return transaction },
      async resolveOperation() { return null },
    },
    accountsService: { async list() { accountsStartedCallback(); return [validAccountDto()] } },
    categoriesService: { async listActive() { categoriesStartedCallback(); return [validCategoryDto({ transaction_type: 'expense' })] } },
  })
  try {
    let initialQuery
    await act(async () => {
      ;[initialQuery] = await Promise.all([initialStarted, accountsStarted, categoriesStarted])
    })
    assert.deepEqual(initialQuery, { offset: 0, limit: 50 })
    assert.equal(listCalls, 1)
    const searchInput = mounted.document.querySelector('[aria-label="Search this page of transactions"]')
    assert.ok(searchInput)
    const setSearchValue = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(searchInput), 'value').set
    setSearchValue.call(searchInput, 'Freshly created')
    await act(async () => searchInput.dispatchEvent(new mounted.window.Event('input', { bubbles: true })))

    const savedNotice = new Promise((resolve) => {
      const observer = new mounted.window.MutationObserver(() => {
        if (mounted.document.body.textContent.includes('Transaction saved to your account')) {
          observer.disconnect()
          resolve()
        }
      })
      observer.observe(mounted.document.body, { childList: true, subtree: true, characterData: true })
    })
    await mounted.clickButton('Add transaction')
    await mounted.setInput('transaction-description', 'Freshly created transaction')
    await mounted.setInput('transaction-amount', '12.50')
    await mounted.submit()
    await act(async () => { await savedNotice })
    assert.equal(postCalls, 1)

    let refreshedQuery
    await act(async () => {
      refreshedQuery = await freshStarted
      await Promise.resolve()
    })
    assert.equal(listCalls, 2, 'The post-create refresh must not reuse the initial GET')
    assert.deepEqual(refreshedQuery, initialQuery)

    await act(async () => resolveFreshList(validTransactionPage([transaction], { total: 1, offset: 0, limit: 50 })))
    assert.match(mounted.document.body.textContent, /Freshly created transaction/)
    assert.equal(searchInput.value, 'Freshly created')

    await act(async () => resolveInitialList(validTransactionPage([], { total: 0, offset: 0, limit: 50 })))
    assert.match(mounted.document.body.textContent, /Freshly created transaction/)
    assert.equal(searchInput.value, 'Freshly created')
    assert.doesNotMatch(mounted.document.body.textContent, /No transactions yet/)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted transactions page closes the dialog after create when account refresh fails', async () => {
  let accountCalls = 0
  let postCalls = 0
  const transaction = validTransactionDto({ description: 'Saved before account refresh failure' })
  const mounted = await mountTransactionsPage({
    service: {
      async list(query) { return validTransactionPage([transaction], { total: 1, offset: query.offset, limit: query.limit }) },
      async create() { postCalls += 1; return transaction },
      async resolveOperation() { return null },
    },
    accountsService: { async list() {
      accountCalls += 1
      if (accountCalls === 2) throw new ApiError(503, 'Account refresh failed.')
      return [validAccountDto()]
    } },
    categoriesService: { async listActive() { return [validCategoryDto({ transaction_type: 'expense' })] } },
  })
  try {
    await mounted.flush()
    await mounted.clickButton('Add transaction')
    await mounted.flush()
    assert.ok(mounted.document.querySelector('#transaction-description'))
    await mounted.setInput('transaction-description', 'Saved before account refresh failure')
    await mounted.setInput('transaction-amount', '12.50')
    await mounted.submit()
    await mounted.flush()
    assert.equal(postCalls, 1)
    assert.equal(mounted.document.querySelector('#transaction-description'), null)
    assert.match(mounted.document.body.textContent, /Transaction saved to your account/)
    assert.match(mounted.document.body.textContent, /Account data could not be loaded: Account refresh failed/)

    await mounted.clickButton('Retry accounts')
    await mounted.flush()
    assert.equal(accountCalls, 3)
    assert.equal(postCalls, 1)
    assert.doesNotMatch(mounted.document.body.textContent, /Account data could not be loaded/)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('recovered uncertain dialog can be replaced and closed without stale parent uncertainty', async () => {
  let resolutionCalls = 0
  let postCalls = 0
  const existing = validTransactionDto({ description: 'Recovered after timeout' })
  const mounted = await mountTransactionsPage({
    service: {
      async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
      async create() { postCalls += 1; throw new ApiNetworkError() },
      async resolveOperation() { resolutionCalls += 1; return existing },
    },
    accountsService: { async list() { return [validAccountDto()] } },
    categoriesService: { async listActive() { return [validCategoryDto({ transaction_type: 'expense' })] } },
  })
  try {
    await mounted.flush()
    await mounted.clickButton('Add transaction')
    await mounted.flush()
    await mounted.setInput('transaction-description', 'Recovered after timeout')
    await mounted.setInput('transaction-amount', '12.50')
    await mounted.submit()
    await mounted.flush()
    assert.equal(postCalls, 1)
    assert.ok(mounted.document.querySelector('#transaction-description'))
    assert.ok([...mounted.document.querySelectorAll('button')].some((button) => button.textContent.includes('Retry recovery')))

    await mounted.clickButton('Retry recovery')
    await mounted.flush()
    assert.equal(mounted.document.querySelector('#transaction-description'), null, 'Successful recovery should remove the transaction form')
    assert.match(mounted.document.body.textContent, /previously submitted transaction was found and recovered/i)

    await mounted.clickButton('Add transaction')
    await mounted.flush()
    const reopenedDialog = mounted.document.querySelector('[role="dialog"]')
    assert.ok(reopenedDialog, 'Expected the transaction dialog to open')
    const dialogTitleId = reopenedDialog.getAttribute('aria-labelledby')
    assert.equal(mounted.document.getElementById(dialogTitleId)?.textContent, 'Add transaction')
    assert.ok(mounted.document.querySelector('#transaction-description'))
    await mounted.setInput('transaction-description', 'A new transaction')
    assert.equal(mounted.document.querySelector('#transaction-description').value, 'A new transaction')
    await mounted.clickButton('Cancel')
    await mounted.flush()
    assert.equal(mounted.document.querySelector('#transaction-description'), null, 'Cancel should remove the transaction form')
    assert.equal(postCalls, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('unrecoverable marker requires explicit reconciliation confirmation before a new transaction', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const storageKey = `vibewealth:pending-transaction:v1:${userId}`
  const mounted = await mountTransactionsPage({
    service: {
      async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
      async create() { assert.fail('No transaction before explicit reconciliation') },
      async resolveOperation() { assert.fail('Malformed JSON has no safe operation key') },
    },
    accountsService: { async list() { return [validAccountDto()] } },
    categoriesService: { async listActive() { return [validCategoryDto({ transaction_type: 'expense' })] } },
    pendingRecord: '{malformed marker',
  })
  try {
    await mounted.flush()
    assert.match(mounted.document.body.textContent, /Automatic recovery is impossible/i)
    assert.match(mounted.document.body.textContent, /cannot prove whether an unidentified operation was saved/i)
    let confirmations = 0
    mounted.window.confirm = (message) => { confirmations += 1; assert.match(message, /duplicate prevention.*cannot be guaranteed/i); return false }
    await mounted.clickButton('I inspected history; abandon marker')
    assert.equal(confirmations, 1)
    assert.equal(mounted.storage.getItem(storageKey), '{malformed marker')
    mounted.window.confirm = () => true
    await mounted.clickButton('I inspected history; abandon marker')
    assert.equal(mounted.storage.getItem(storageKey), null)
    assert.match(mounted.document.body.textContent, /duplicate prevention cannot be guaranteed/i)
    await mounted.clickButton('Add transaction')
    assert.ok(mounted.document.querySelector('#transaction-description'))
  } finally { await mounted.unmount(); mounted.close() }
})

test('resolved different-payload idempotency conflict is not reported as the submitted transaction', async () => {
  const calls = []
  const original = validTransactionDto({ description: 'Original committed details', amount_paise: 2500 })
  const mounted = await mountTransactionsPage({
    service: {
      async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
      async create(input, key) {
        calls.push({ input, key })
        if (calls.length === 1) throw new ApiError(409, 'Idempotency-Key was already used for a different transaction')
        return validTransactionDto({
          account_id: input.account_id,
          category_id: input.category_id,
          transaction_type: input.transaction_type,
          amount_paise: input.amount_paise,
          description: input.description,
          transaction_date: input.transaction_date,
          notes: input.notes ?? null,
        })
      },
      async resolveOperation(key) {
        assert.equal(key, calls[0].key)
        return original
      },
    },
    accountsService: { async list() { return [validAccountDto()] } },
    categoriesService: { async listActive() { return [validCategoryDto({ transaction_type: 'expense' })] } },
  })
  try {
    await mounted.flush()
    await mounted.clickButton('Add transaction')
    await mounted.flush()
    await mounted.setInput('transaction-description', 'Different retry details')
    await mounted.setInput('transaction-amount', '12.50')
    await mounted.submit()
    await mounted.flush()

    assert.equal(calls.length, 1)
    assert.match(mounted.document.body.textContent, /previous transaction was saved with different details/i)
    assert.doesNotMatch(mounted.document.body.textContent, /Transaction saved to your account/)
    assert.ok(mounted.document.querySelector('#transaction-description'))

    await mounted.submit()
    await mounted.flush()
    assert.equal(calls.length, 2)
    assert.notEqual(calls[1].key, calls[0].key)
    assert.equal(mounted.document.querySelector('#transaction-description'), null)
    assert.match(mounted.document.body.textContent, /Transaction saved to your account/)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('transaction provider clamps an out-of-range page and fetches the valid page', async () => {
  const queries = []
  const service = {
    async list(query) {
      queries.push(query.offset)
      return query.offset === 50
        ? validTransactionPage([], { total: 45, offset: 50, limit: 50 })
        : validTransactionPage([validTransactionDto()], { total: 45, offset: 0, limit: 50 })
    },
    async create() { return validTransactionDto() },
  }
  const mounted = await mountTransactionsProvider(service)
  try {
    await mounted.flush()
    await act(async () => mounted.transactions.setOffset(50))
    await mounted.flush()
    assert.deepEqual(queries, [0, 50, 0])
    assert.equal(mounted.transactions.query.offset, 0)
    assert.equal(mounted.transactions.list.data.items.length, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted transaction provider isolates stale list results after an auth-session change', async () => {
  let resolveOldList
  let listCalls = 0
  const service = {
    list() {
      listCalls += 1
      if (listCalls === 1) return new Promise((resolve) => { resolveOldList = resolve })
      return Promise.resolve(validTransactionPage([validTransactionDto({ description: 'New session transaction' })]))
    },
    async create() { return validTransactionDto() },
  }
  const mounted = await mountTransactionsProvider(service)
  try {
    await mounted.flush()
    await act(async () => mounted.rerender(2))
    await mounted.flush()
    assert.equal(mounted.transactions.list.data.items[0].description, 'New session transaction')
    await act(async () => resolveOldList(validTransactionPage([validTransactionDto({ description: 'Old private transaction' })])))
    assert.equal(mounted.transactions.list.data.items[0].description, 'New session transaction')
    assert.equal(mounted.transactions.list.data.items.some((item) => item.description === 'Old private transaction'), false)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted transaction provider coalesces duplicate create submissions', async () => {
  let resolveCreate
  let createCalls = 0
  const service = {
    list: async () => validTransactionPage(),
    create: () => {
      createCalls += 1
      return new Promise((resolve) => { resolveCreate = resolve })
    },
  }
  const mounted = await mountTransactionsProvider(service)
  const input = {
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense',
    amount_paise: 500,
    description: 'Duplicate prevention',
    transaction_date: '2026-01-02',
  }
  try {
    await mounted.flush()
    let first
    let second
    await act(async () => {
      first = mounted.transactions.createTransaction(input, 'test-operation-key-0002')
      second = mounted.transactions.createTransaction(input, 'test-operation-key-0002')
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    assert.equal(createCalls, 1)
    assert.equal(mounted.isCreating, true)
    resolveCreate(validTransactionDto())
    await act(async () => Promise.all([first, second]))
    assert.equal(mounted.isCreating, false)
    assert.equal(createCalls, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('transaction provider deduplicates concurrent list requests for the same query', async () => {
  let notifyListStarted
  const listStarted = new Promise((resolve) => { notifyListStarted = resolve })
  let resolveList
  let listCalls = 0
  const service = {
    list(query) {
      listCalls += 1
      notifyListStarted({ ...query })
      return new Promise((resolve) => { resolveList = resolve })
    },
    async create() { return validTransactionDto() },
  }
  const mounted = await mountTransactionsProvider(service)
  try {
    let initialQuery
    await act(async () => { initialQuery = await listStarted })
    let duplicateRequest
    await act(async () => { duplicateRequest = mounted.transactions.retryList() })
    assert.equal(listCalls, 1)

    await act(async () => resolveList(validTransactionPage([], { total: 0, offset: 0, limit: 50 })))
    await act(async () => duplicateRequest)
    assert.deepEqual(initialQuery, { offset: 0, limit: 50 })
    assert.equal(mounted.transactions.list.status, 'success')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('transaction provider recovers a durable pending operation after keyed provider teardown', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const key = 'secure-pending-operation-key-01'
  let committed = false
  let postCalls = 0
  let resolvedKey
  const transaction = validTransactionDto({ description: 'Committed before response loss' })
  const service = {
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create() {
      postCalls += 1
      committed = true
      throw new ApiNetworkError()
    },
    async resolveOperation(operationKey) {
      resolvedKey = operationKey
      return committed ? transaction : null
    },
  }
  const mounted = await mountTransactionsProvider(service, { userId })
  const input = {
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense',
    amount_paise: 2500,
    description: 'Committed before response loss',
    transaction_date: '2026-01-02',
  }
  try {
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'ready')
    await act(async () => assert.rejects(mounted.transactions.createTransaction(input, key), ApiNetworkError))
    assert.equal(postCalls, 1)
    const storedOperation = JSON.parse(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userId}`))
    assert.deepEqual(Object.keys(storedOperation).sort(), ['key', 'userId', 'version'])
    assert.equal(storedOperation.key, key)
    assert.equal(JSON.stringify(storedOperation).includes(input.description), false)

    await act(async () => mounted.rerender(2, userId))
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'recovered')
    assert.equal(resolvedKey, key)
    assert.equal(postCalls, 1)
    assert.equal(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userId}`), null)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('uncertain transaction outcomes retain and retry the identical operation key', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const storageKey = `vibewealth:pending-transaction:v1:${userId}`
  const input = { account_id: validAccountDto().id, category_id: validCategoryDto({ transaction_type: 'expense' }).id, transaction_type: 'expense', amount_paise: 100, description: 'Retry safely', transaction_date: '2026-01-02' }
  for (const failure of [new ApiError(408, 'Timeout'), new ApiError(418, 'Unexpected response'), new ApiError(503, 'Unavailable'), new ApiNetworkError()]) {
    const key = `same-operation-key-${Math.random().toString(36).slice(2, 12)}`
    const calls = []
    const service = {
      async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
      async create(_input, submittedKey) { calls.push(submittedKey); if (calls.length === 1) throw failure; return validTransactionDto() },
      async resolveOperation() { return null },
    }
    const mounted = await mountTransactionsProvider(service, { userId })
    try {
      await mounted.flush()
      await act(async () => assert.rejects(mounted.transactions.createTransaction(input, key)))
      assert.equal(JSON.parse(mounted.storage.getItem(storageKey)).key, key)
      assert.equal(mounted.recoveryStatus, 'error')
      await act(async () => mounted.transactions.createTransaction(input, key))
      assert.deepEqual(calls, [key, key])
      assert.equal(mounted.storage.getItem(storageKey), null)
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  }
})

test('definitive backend validation rejection clears its pending operation', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const key = 'definitive-validation-operation-01'
  const mounted = await mountTransactionsProvider({
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create() { throw new ApiError(422, 'Invalid transaction') },
    async resolveOperation() { return null },
  }, { userId })
  try {
    await mounted.flush()
    await act(async () => assert.rejects(mounted.transactions.createTransaction({ account_id: validAccountDto().id, category_id: validCategoryDto({ transaction_type: 'expense' }).id, transaction_type: 'expense', amount_paise: 100, description: 'Invalid', transaction_date: '2026-01-02' }, key)))
    assert.equal(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userId}`), null)
    assert.equal(mounted.recoveryStatus, 'ready')
  } finally { await mounted.unmount(); mounted.close() }
})

test('a safely extractable unsupported marker is resolved before it can be abandoned', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const key = 'future-operation-key-0001'
  const resolved = validTransactionDto()
  const mounted = await mountTransactionsProvider({
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create() { assert.fail('Unsupported marker must not cause a new POST') },
    async resolveOperation(receivedKey) { assert.equal(receivedKey, key); return resolved },
  }, { userId, pendingRecord: { version: 99, userId, key } })
  try {
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'recovered')
    assert.equal(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userId}`), null)
  } finally { await mounted.unmount(); mounted.close() }
})

test('pending transaction keys remain user-scoped across logout and same-user reauthentication', async () => {
  const userA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const userB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
  const key = 'secure-pending-operation-key-02'
  let committed = false
  let postCalls = 0
  const resolutionCalls = []
  const service = {
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create() { postCalls += 1; committed = true; throw new ApiNetworkError() },
    async resolveOperation(operationKey) {
      resolutionCalls.push(operationKey)
      return committed ? validTransactionDto() : null
    },
  }
  const mounted = await mountTransactionsProvider(service, { userId: userA })
  try {
    await mounted.flush()
    await act(async () => assert.rejects(mounted.transactions.createTransaction({
      account_id: validAccountDto().id,
      category_id: validCategoryDto({ transaction_type: 'expense' }).id,
      transaction_type: 'expense', amount_paise: 100, description: 'Pending', transaction_date: '2026-01-02',
    }, key), ApiNetworkError))
    await act(async () => mounted.rerender(2, userB))
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'ready')
    assert.deepEqual(resolutionCalls, [])
    assert.notEqual(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userA}`), null)

    await act(async () => mounted.rerender(3, userA))
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'recovered')
    assert.deepEqual(resolutionCalls, [key])
    assert.equal(postCalls, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('unreadable pending storage blocks a new transaction without replacing the record', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  let postCalls = 0
  const service = {
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create() { postCalls += 1; return validTransactionDto() },
    async resolveOperation() { return null },
  }
  const mounted = await mountTransactionsProvider(service, { userId })
  const storageKey = `vibewealth:pending-transaction:v1:${userId}`
  try {
    mounted.storage.setItem(storageKey, '{obsolete or malformed')
    await mounted.rerender(2, userId)
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'invalid')
    await act(async () => assert.rejects(mounted.transactions.createTransaction({
      account_id: validAccountDto().id,
      category_id: validCategoryDto({ transaction_type: 'expense' }).id,
      transaction_type: 'expense', amount_paise: 100, description: 'Must not post', transaction_date: '2026-01-02',
    }, 'secure-pending-operation-key-03')))
    assert.equal(postCalls, 0)
    assert.equal(mounted.storage.getItem(storageKey), '{obsolete or malformed')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('confirmed not-found recovery reuses the stored operation key for the next POST', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const key = 'secure-pending-operation-key-04'
  let postedKey
  const service = {
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create(_input, operationKey) { postedKey = operationKey; return validTransactionDto() },
    async resolveOperation(operationKey) { assert.equal(operationKey, key); return null },
  }
  const mounted = await mountTransactionsProvider(service, {
    userId,
    pendingRecord: { version: 1, userId, key },
  })
  const input = {
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense', amount_paise: 100, description: 'Retry same operation', transaction_date: '2026-01-02',
  }
  try {
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'not-found')
    assert.equal(mounted.transactions.pendingOperationKey, key)
    await act(async () => mounted.transactions.createTransaction(input, key))
    assert.equal(postedKey, key)
    assert.equal(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userId}`), null)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('failed operation resolution preserves the key and blocks a new logical transaction', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const key = 'secure-pending-operation-key-06'
  let resolutionCalls = 0
  let postCalls = 0
  const service = {
    async list(query) { return validTransactionPage([], { total: 0, offset: query.offset, limit: query.limit }) },
    async create() { postCalls += 1; return validTransactionDto() },
    async resolveOperation() {
      resolutionCalls += 1
      if (resolutionCalls === 1) throw new ApiNetworkError()
      return null
    },
  }
  const mounted = await mountTransactionsProvider(service, {
    userId,
    pendingRecord: { version: 1, userId, key },
  })
  try {
    await mounted.flush()
    assert.equal(mounted.recoveryStatus, 'error')
    assert.equal(mounted.transactions.pendingOperationKey, key)
    await act(async () => assert.rejects(mounted.transactions.createTransaction({
      account_id: validAccountDto().id,
      category_id: validCategoryDto({ transaction_type: 'expense' }).id,
      transaction_type: 'expense', amount_paise: 100, description: 'Blocked', transaction_date: '2026-01-02',
    }, 'secure-pending-operation-key-07')))
    assert.equal(postCalls, 0)
    assert.equal(mounted.storage.getItem(`vibewealth:pending-transaction:v1:${userId}`) !== null, true)
    await act(async () => mounted.transactions.retryOperationResolution())
    assert.equal(mounted.recoveryStatus, 'not-found')
    assert.equal(mounted.transactions.pendingOperationKey, key)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('a pending create from an old session cannot refresh or update the next session', async () => {
  let resolveCreate
  let refreshCount = 0
  let listCalls = 0
  const service = {
    list: async () => {
      listCalls += 1
      return validTransactionPage([validTransactionDto({ description: listCalls === 1 ? 'Old session' : 'New session' })])
    },
    create: () => new Promise((resolve) => { resolveCreate = resolve }),
  }
  const mounted = await mountTransactionsProvider(service, { retryAccounts: async () => { refreshCount += 1 } })
  const input = {
    account_id: validAccountDto().id,
    category_id: validCategoryDto({ transaction_type: 'expense' }).id,
    transaction_type: 'expense',
    amount_paise: 500,
    description: 'Old-session submission',
    transaction_date: '2026-01-02',
  }
  try {
    await mounted.flush()
    let pendingCreate
    await act(async () => {
      pendingCreate = mounted.transactions.createTransaction(input, 'test-operation-key-0003')
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    await act(async () => mounted.rerender(2))
    await mounted.flush()
    assert.equal(mounted.transactions.list.data.items[0].description, 'New session')
    resolveCreate(validTransactionDto({ description: 'Old-session submission' }))
    await act(async () => pendingCreate)
    assert.equal(mounted.transactions.list.data.items[0].description, 'New session')
    assert.equal(refreshCount, 0)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('a transaction-list 401 invokes the existing authentication lifecycle', async () => {
  let logoutCalls = 0
  const mounted = await mountTransactionsProvider({
    list: async () => { throw new ApiError(401, 'Your session is no longer valid. Please sign in again.') },
    create: async () => validTransactionDto(),
  }, { onUnauthorized: async () => { logoutCalls += 1 } })
  try {
    await mounted.flush()
    assert.equal(mounted.status, 'error')
    assert.equal(logoutCalls, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('Transactions page renders backend records and resource states without sample transaction fallback', () => {
  const account = validAccountDto()
  const categories = [validCategoryDto({ transaction_type: 'expense' }), validCategoryDto({ id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', name: 'Salary', transaction_type: 'income' })]
  const transaction = validTransactionDto({ description: 'Backend transaction only' })
  const renderPage = (listState, query = { offset: 0, limit: 50 }) => renderToString(createElement(
    AccountCategoryContext.Provider,
    { value: {
      accounts: { status: 'success', data: [account], error: null },
      categories: { status: 'success', data: categories, error: null },
      retryAccounts: async () => {},
      retryCategories: async () => {},
    } },
    createElement(FinanceContext.Provider, { value: { preferences: { currency: 'INR' } } },
      createElement(TransactionsContext.Provider, { value: {
        list: listState,
        query,
        isCreating: false,
        recovery: { status: 'ready', message: null, transaction: null },
        pendingOperationKey: null,
        setFilters() {},
        setOffset() {},
        resetFilters() {},
        retryList: async () => {},
        retryOperationResolution: async () => null,
        createTransaction: async () => {},
      } }, createElement(TransactionsPage)),
    ),
  ))

  const successMarkup = renderPage({ status: 'success', data: validTransactionPage([transaction]), error: null })
  assert.match(successMarkup, /Backend transaction only/)
  assert.match(successMarkup, /Primary account/)
  assert.match(successMarkup, /Food/)
  assert.match(successMarkup, /Search this page of transactions/)
  assert.doesNotMatch(successMarkup, /Coffee and pastry/)

  const emptyMarkup = renderPage({ status: 'success', data: validTransactionPage([], { total: 0 }), error: null })
  assert.match(emptyMarkup, /No transactions yet/)
  const filteredEmptyMarkup = renderPage(
    { status: 'success', data: validTransactionPage([], { total: 0 }), error: null },
    { offset: 0, limit: 50, transaction_type: 'expense' },
  )
  assert.match(filteredEmptyMarkup, /No transactions match/)
  assert.doesNotMatch(filteredEmptyMarkup, /No transactions yet/)
  assert.match(renderPage({ status: 'loading', data: null, error: null }), /Loading transactions/)
  assert.match(renderPage({ status: 'error', data: null, error: 'Temporary list failure' }), /Temporary list failure/)
})

test('mounted transaction form submits backend account/category IDs and retains values after rejection', async () => {
  let submitted
  const mounted = await mountTransactionForm(async (input) => {
    submitted = input
    throw new ApiError(422, 'Expense exceeds available-to-spend for this account.')
  })
  try {
    await mounted.setInput('transaction-description', 'Groceries')
    await mounted.setInput('transaction-amount', '123.45')
    await mounted.submit()
    assert.equal(submitted.account_id, validAccountDto().id)
    assert.equal(submitted.category_id, validCategoryDto({ transaction_type: 'expense' }).id)
    assert.equal(submitted.transaction_type, 'expense')
    assert.equal(submitted.amount_paise, 12345)
    assert.equal(submitted.description, 'Groceries')
    assert.match(mounted.document.querySelector('[role="alert"]').textContent, /available-to-spend/)
    assert.equal(mounted.document.querySelector('#transaction-description').value, 'Groceries')
    assert.equal(mounted.document.querySelector('#transaction-amount').value, '123.45')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('ambiguous transaction failure preserves and retries the same operation key and payload', async () => {
  const submissions = []
  const mounted = await mountTransactionForm(async (input, key) => {
    submissions.push({ input, key })
    if (submissions.length === 1) throw new ApiNetworkError()
  })
  try {
    await mounted.setInput('transaction-description', 'Retry safely')
    await mounted.setInput('transaction-amount', '25.00')
    await mounted.submit()
    assert.match(mounted.document.querySelector('[role="alert"]').textContent, /could not confirm whether this transaction was saved/i)
    assert.equal(mounted.document.querySelector('#transaction-description').disabled, true)
    assert.equal(mounted.document.querySelector('button[type="submit"]').textContent, 'Retry same transaction')
    await mounted.submit()
    assert.equal(submissions.length, 2)
    assert.equal(submissions[0].key, submissions[1].key)
    assert.deepEqual(submissions[0].input, submissions[1].input)
    assert.equal(mounted.document.querySelector('[role="alert"]'), null)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('transaction form reuses a recovered pending key instead of generating a new one', async () => {
  let submission
  const key = 'secure-pending-operation-key-05'
  const mounted = await mountTransactionForm(async (input, operationKey) => {
    submission = { input, operationKey }
  }, { recoveryOperationKey: key })
  try {
    await mounted.setInput('transaction-description', 'Recovered submission')
    await mounted.setInput('transaction-amount', '25.00')
    await mounted.submit()
    assert.equal(submission.operationKey, key)
    assert.equal(submission.input.description, 'Recovered submission')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})


test('API base URL uses the local default and trims configured trailing slashes', () => {
  assert.equal(getApiBaseUrl(undefined), 'http://localhost:8000')
  assert.equal(getApiBaseUrl('https://api.example.test/'), 'https://api.example.test')
  assert.equal(getApiBaseUrl('   '), 'http://localhost:8000')
})

test('API requests include cookies and only send JSON and CSRF headers when needed', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000/', async (url, options) => {
    calls.push({ url: String(url), options })
    return jsonResponse({ ok: true })
  })

  await client.request('/api/accounts')
  client.setCsrfToken('in-memory-token')
  await client.request('/api/auth/logout', {
    method: 'POST',
    body: { done: true },
  })

  assert.equal(calls[0].url, 'http://localhost:8000/api/accounts')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.redirect, 'error')
  assert.equal(calls[0].options.headers.has('Content-Type'), false)
  assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false)
  assert.equal(calls[1].options.credentials, 'include')
  assert.equal(calls[1].options.redirect, 'error')
  assert.equal(calls[1].options.headers.get('Content-Type'), 'application/json')
  assert.equal(calls[1].options.headers.get('X-CSRF-Token'), 'in-memory-token')
  assert.equal(calls[1].options.body, JSON.stringify({ done: true }))
})

test('API client accepts same-origin request URLs and preserves public auth query strings', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: String(url), options })
    return jsonResponse({ ok: true })
  })
  await client.request('/api/accounts?limit=10')
  await client.request('http://localhost:8000/api/auth/login?next=%2Fdashboard', {
    method: 'POST', body: { email: 'person@example.test', password: 'secret' },
  })
  await client.request('/api/auth/register?source=onboarding', {
    method: 'POST', body: { email: 'person@example.test', password: 'secret' },
  })
  assert.equal(calls.length, 3)
  assert.equal(calls[0].url, 'http://localhost:8000/api/accounts?limit=10')
  assert.equal(calls[1].url, 'http://localhost:8000/api/auth/login?next=%2Fdashboard')
  assert.equal(calls[2].url, 'http://localhost:8000/api/auth/register?source=onboarding')
  assert.ok(calls.every(({ options }) => options.credentials === 'include'))
  assert.ok(calls.every(({ options }) => !options.headers.has('X-CSRF-Token')))
})

test('API client rejects external and protocol-relative URLs before fetch or CSRF attachment', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: String(url), options })
    return jsonResponse({ ok: true })
  })
  client.setCsrfToken('must-not-leave-this-origin')

  for (const path of [
    'https://attacker.example/api/accounts',
    '//attacker.example/api/accounts',
    'https://attacker.example/api/auth/login',
    'https://attacker.example/api/auth/register',
  ]) {
    await assert.rejects(client.request(path, { method: 'POST', body: { secret: true } }), ApiUrlError)
  }
  assert.equal(calls.length, 0, 'no rejected URL reaches fetch with credentials or a CSRF header')
})

test('only exact public auth POST paths are CSRF-exempt after URL normalization', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: String(url), options })
    return jsonResponse({ ok: true })
  })

  for (const path of ['/api/auth/login/', '/api/auth/%6cogin', '/api/auth/login/extra', '/api/auth/register/']) {
    await assert.rejects(client.request(path, { method: 'POST' }), ApiCsrfError)
  }
  await assert.rejects(client.request('/api/auth/login', { method: 'PUT' }), ApiCsrfError)
  assert.equal(calls.length, 0)

  client.setCsrfToken('csrf-token')
  await client.request('/api/auth/login/', { method: 'POST' })
  await client.request('/api/auth/%6cogin', { method: 'POST' })
  await client.request('/api/auth/login', { method: 'PUT' })
  assert.equal(calls.length, 3)
  assert.ok(calls.every(({ options }) => options.headers.get('X-CSRF-Token') === 'csrf-token'))
})

test('shared API client enforces CSRF except for the exact public login and registration posts', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ path: new URL(String(url)).pathname, options })
    return jsonResponse({ ok: true })
  })

  await client.request('/api/accounts')
  await client.request('/api/auth/login', { method: 'POST', body: { email: 'x', password: 'y' } })
  await client.request('/api/auth/register', { method: 'POST', body: { email: 'x', password: 'y' } })
  client.setCsrfToken('valid-session-token')
  await client.request('/api/accounts/account-id', { method: 'PATCH', body: { name: 'New name' } })
  await client.request('/api/auth/logout', { method: 'POST' })

  assert.deepEqual(calls.map(({ path }) => path), [
    '/api/accounts', '/api/auth/login', '/api/auth/register',
    '/api/accounts/account-id', '/api/auth/logout',
  ])
  assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false)
  assert.equal(calls[1].options.headers.has('X-CSRF-Token'), false)
  assert.equal(calls[2].options.headers.has('X-CSRF-Token'), false)
  assert.equal(calls[3].options.headers.get('X-CSRF-Token'), 'valid-session-token')
  assert.equal(calls[4].options.headers.get('X-CSRF-Token'), 'valid-session-token')
  assert.ok(calls.every(({ options }) => options.credentials === 'include'))

  let unauthorizedFetches = 0
  const noTokenClient = new ApiClient('http://localhost:8000', async () => {
    unauthorizedFetches += 1
    return jsonResponse({ ok: true })
  })
  await assert.rejects(
    noTokenClient.request('/api/accounts/account-id', { method: 'PATCH', body: { name: 'No token' } }),
    ApiCsrfError,
  )
  await assert.rejects(
    noTokenClient.request('/api/finance/write', { method: 'POST', body: {} }),
    ApiCsrfError,
  )
  assert.equal(unauthorizedFetches, 0)
})

test('API client handles empty responses, backend validation errors, and network failures', async () => {
  const emptyClient = new ApiClient('http://localhost:8000', async () => new Response(null, { status: 204 }))
  emptyClient.setCsrfToken('session-token')
  assert.equal(await emptyClient.request('/api/auth/logout', { method: 'POST' }), undefined)

  const validationClient = new ApiClient('http://localhost:8000', async () => jsonResponse({
    detail: [{ loc: ['body', 'email'], msg: 'Enter a valid email address' }],
  }, 422))
  await assert.rejects(
    validationClient.request('/api/auth/register', { method: 'POST', body: {} }),
    (error) => error instanceof ApiError && error.status === 422 && /email: Enter a valid email/.test(error.message),
  )

  const serverClient = new ApiClient('http://localhost:8000', async () => jsonResponse({
    detail: 'Traceback (most recent call last): secret internals',
  }, 500))
  await assert.rejects(
    serverClient.request('/api/auth/me'),
    (error) => error instanceof ApiError && !/Traceback|secret internals/.test(error.message),
  )

  const networkClient = new ApiClient('http://localhost:8000', async () => {
    throw new TypeError('socket details are not shown to the user')
  })
  await assert.rejects(networkClient.request('/api/auth/me'), ApiNetworkError)
})

test('API redirects fail closed and a rejected mutation is never replayed', async () => {
  let mutationCount = 0
  let refreshCount = 0
  const client = new ApiClient('http://localhost:8000', async (_url, options) => {
    mutationCount += 1
    assert.equal(options.redirect, 'error')
    throw new TypeError('redirect blocked')
  })
  client.setCsrfToken('session-token')
  client.setCsrfRefreshHandler(async () => { refreshCount += 1 })

  await assert.rejects(
    client.request('/api/transactions', {
      method: 'POST', body: { amount_paise: 100 }, redirect: 'follow',
    }),
    ApiNetworkError,
  )
  assert.equal(mutationCount, 1)
  assert.equal(refreshCount, 0)
})

test('a rejected stale CSRF token is refreshed without replaying the mutation', async () => {
  let mutationCount = 0
  let refreshCount = 0
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    if (new URL(String(url)).pathname === '/api/auth/csrf') {
      refreshCount += 1
      return jsonResponse({ csrf_token: 'fresh-token' })
    }
    mutationCount += 1
    assert.equal(options.headers.get('X-CSRF-Token'), 'stale-token')
    return jsonResponse({ detail: 'CSRF validation failed' }, 403)
  })
  new AuthApi(client)
  client.setCsrfToken('stale-token')

  await assert.rejects(
    client.request('/api/auth/logout', { method: 'POST' }),
    (error) => error instanceof ApiError && /token was refreshed/.test(error.message),
  )
  assert.equal(mutationCount, 1)
  assert.equal(refreshCount, 1)
})

test('concurrent stale CSRF responses share one refresh and never replay either mutation', async () => {
  let mutationCount = 0
  let refreshCount = 0
  let resolveCsrfResponse
  const csrfResponse = new Promise((resolve) => { resolveCsrfResponse = resolve })
  const client = new ApiClient('http://localhost:8000', async (url) => {
    if (new URL(String(url)).pathname === '/api/auth/csrf') {
      refreshCount += 1
      return csrfResponse
    }
    mutationCount += 1
    return jsonResponse({ detail: 'CSRF validation failed' }, 403)
  })
  new AuthApi(client)
  client.setCsrfToken('stale-session-token')

  const pending = Promise.allSettled([
    client.request('/api/accounts/a', { method: 'PATCH', body: { name: 'A' } }),
    client.request('/api/accounts/b', { method: 'PATCH', body: { name: 'B' } }),
  ])
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(mutationCount, 2)
  assert.equal(refreshCount, 1)
  resolveCsrfResponse(jsonResponse({ csrf_token: 'fresh-session-token' }))
  const results = await pending
  assert.ok(results.every((result) => result.status === 'rejected' && result.reason instanceof ApiError))
  assert.equal(mutationCount, 2)
  assert.equal(refreshCount, 1)
})

test('auth API restores a session, obtains CSRF in memory, and treats 401 as signed out', async () => {
  const user = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', email: 'person@example.test', display_name: 'Person' }
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    const path = new URL(String(url)).pathname
    calls.push({ path, options })
    if (path === '/api/auth/me') return jsonResponse(user)
    if (path === '/api/auth/csrf') return jsonResponse({ csrf_token: 'session-csrf' })
    throw new Error(`Unexpected path ${path}`)
  })
  const auth = new AuthApi(client)

  const firstRestore = auth.restoreSession()
  const repeatedRestore = auth.restoreSession()
  assert.strictEqual(repeatedRestore, firstRestore)
  assert.deepEqual(await firstRestore, user)
  assert.deepEqual(calls.map((call) => call.path), ['/api/auth/me', '/api/auth/csrf'])
  assert.ok(calls.every((call) => call.options.credentials === 'include'))
  assert.ok(calls.every((call) => !call.options.headers.has('X-CSRF-Token')))

  const unauthorized = new AuthApi(new ApiClient('http://localhost:8000', async () => (
    jsonResponse({ detail: 'Authentication required' }, 401)
  )))
  assert.equal(await unauthorized.restoreSession(), null)
})

test('account and active-category APIs preserve backend DTOs and endpoint paths', async () => {
  const account = {
    id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    name: 'Primary',
    account_type: 'bank',
    is_default: true,
    opening_balance_paise: 4500,
    opening_balance_as_of: '2026-01-01',
    balance_paise: 4500,
    goal_allocated_paise: 0,
    available_to_spend_paise: 4500,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
  const category = { id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', name: 'Food', transaction_type: 'expense' }
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    const path = new URL(String(url)).pathname
    calls.push({ path, options })
    if (path === '/api/accounts') return jsonResponse([account])
    if (path === `/api/accounts/${account.id}`) return jsonResponse(account)
    if (path === '/api/categories') return jsonResponse([category])
    throw new Error(`Unexpected path ${path}`)
  })
  const accounts = new AccountsApi(client)
  const categories = new CategoriesApi(client)

  assert.deepEqual(await accounts.list(), [account])
  assert.deepEqual(await accounts.get(account.id), account)
  assert.deepEqual(await categories.listActive(), [category])
  assert.deepEqual(calls.map((call) => call.path), [
    '/api/accounts', `/api/accounts/${account.id}`, '/api/categories',
  ])
  assert.ok(calls.every((call) => call.options.credentials === 'include'))
})

test('account and category data load independently and retain exact paise DTO values', async () => {
  const account = validAccountDto()
  const category = validCategoryDto({ name: 'Rent', transaction_type: 'expense' })
  let accountCalls = 0
  let categoryCalls = 0
  const mounted = await mountAccountCategoryProvider({
    sessionIdentity: { generation: 1 },
    onUnauthorized: async () => {},
    accountsService: { list: async () => { accountCalls += 1; return [account] } },
    categoriesService: { listActive: async () => { categoryCalls += 1; return [validCategoryDto(), category] } },
  })
  try {
    await mounted.flush()
    assert.equal(mounted.accountStatus, 'success')
    assert.equal(mounted.categoryStatus, 'success')
    assert.deepEqual(mounted.data.accounts.data, [account])
    assert.deepEqual(mounted.data.categories.data, [validCategoryDto(), category])
    assert.equal(mounted.data.accounts.data[0].balance_paise, Number.MAX_SAFE_INTEGER)
    assert.equal(mounted.data.accounts.data[0].available_to_spend_paise, 9007199254739741)
    assert.equal(accountCalls, 1, 'StrictMode effect replay shares the active account request')
    assert.equal(categoryCalls, 1, 'StrictMode effect replay shares the active category request')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('empty account and category responses produce successful empty states', async () => {
  const mounted = await mountAccountCategoryProvider({
    sessionIdentity: { generation: 1 },
    onUnauthorized: async () => {},
    accountsService: { list: async () => [] },
    categoriesService: { listActive: async () => [] },
  })
  try {
    await mounted.flush()
    assert.equal(mounted.data.accounts.status, 'success')
    assert.deepEqual(mounted.data.accounts.data, [])
    assert.equal(mounted.data.categories.status, 'success')
    assert.deepEqual(mounted.data.categories.data, [])
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('account and category failures are retryable and never fall back to mock finance records', async () => {
  let accountCalls = 0
  let categoryCalls = 0
  const mounted = await mountAccountCategoryProvider({
    sessionIdentity: { generation: 1 },
    onUnauthorized: async () => {},
    accountsService: { list: async () => {
      accountCalls += 1
      if (accountCalls === 1) throw new ApiNetworkError()
      return [validAccountDto()]
    } },
    categoriesService: { listActive: async () => {
      categoryCalls += 1
      if (categoryCalls === 1) throw new ApiError(500, 'The server could not complete the request. Please try again.')
      return [validCategoryDto()]
    } },
  })
  try {
    await mounted.flush()
    assert.equal(mounted.data.accounts.status, 'error')
    assert.equal(mounted.data.categories.status, 'error')
    assert.deepEqual(mounted.data.accounts.data, [])
    assert.deepEqual(mounted.data.categories.data, [])
    assert.match(mounted.data.accounts.error, /Unable to reach VibeWealth/)
    assert.doesNotMatch(JSON.stringify(mounted.data), /Groceries|Coffee|Alex Morgan/)

    await act(async () => Promise.all([mounted.data.retryAccounts(), mounted.data.retryCategories()]))
    assert.equal(mounted.data.accounts.status, 'success')
    assert.equal(mounted.data.categories.status, 'success')
    assert.equal(accountCalls, 2)
    assert.equal(categoryCalls, 2)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('an account or category 401 uses the existing authentication logout flow', async () => {
  let logoutCalls = 0
  const mounted = await mountAccountCategoryProvider({
    sessionIdentity: { generation: 1 },
    onUnauthorized: async () => { logoutCalls += 1 },
    accountsService: { list: async () => { throw new ApiError(401, 'Your session is no longer valid. Please sign in again.') } },
    categoriesService: { listActive: async () => [] },
  })
  try {
    await mounted.flush()
    assert.equal(mounted.data.accounts.status, 'error')
    assert.equal(logoutCalls, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('a new auth-session generation clears pending account and category responses', async () => {
  let resolveOldAccounts
  let resolveOldCategories
  let resolveNewAccounts
  let resolveNewCategories
  const oldSession = {
    sessionIdentity: { generation: 1 },
    onUnauthorized: async () => {},
    accountsService: { list: () => new Promise((resolve) => { resolveOldAccounts = resolve }) },
    categoriesService: { listActive: () => new Promise((resolve) => { resolveOldCategories = resolve }) },
  }
  const newAccount = validAccountDto({
    id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee',
    name: 'New session account',
    balance_paise: 2200,
    available_to_spend_paise: 2200,
  })
  const newCategory = validCategoryDto({
    id: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
    name: 'New session category',
  })
  const newSession = {
    sessionIdentity: { generation: 2 },
    onUnauthorized: async () => {},
    accountsService: { list: () => new Promise((resolve) => { resolveNewAccounts = resolve }) },
    categoriesService: { listActive: () => new Promise((resolve) => { resolveNewCategories = resolve }) },
  }
  const mounted = await mountAccountCategoryProvider(oldSession)
  try {
    await mounted.flush()
    assert.equal(mounted.accountStatus, 'loading')
    await mounted.rerender(newSession)
    assert.equal(mounted.accountStatus, 'loading')
    assert.deepEqual(mounted.data.accounts.data, [])
    assert.deepEqual(mounted.data.categories.data, [])
    resolveNewAccounts([newAccount])
    resolveNewCategories([newCategory])
    await mounted.flush()
    assert.deepEqual(mounted.data.accounts.data, [newAccount])
    assert.deepEqual(mounted.data.categories.data, [newCategory])

    resolveOldAccounts([validAccountDto({ name: 'Stale previous-session account' })])
    resolveOldCategories([validCategoryDto({ name: 'Stale previous-session category' })])
    await mounted.flush()
    assert.deepEqual(mounted.data.accounts.data, [newAccount])
    assert.deepEqual(mounted.data.categories.data, [newCategory])
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('Settings displays backend account values and separates income from expense categories', () => {
  const account = validAccountDto({ balance_paise: 1200, goal_allocated_paise: 800, available_to_spend_paise: 650 })
  const categoryValues = [
    validCategoryDto(),
    validCategoryDto({ id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', name: 'Food', transaction_type: 'expense' }),
  ]
  const repository = new MockFinanceRepository()
  const financeValue = {
    snapshot: repository.getSnapshot(),
    preferences: { currency: 'INR', theme: 'light', budgetAlerts: true, weeklySummary: false },
    updatePreferences: () => {},
    updateProfile: async () => {},
    isMutating: false,
    mutationError: null,
  }
  const accountCategoryValue = {
    accounts: { status: 'success', data: [account], error: null },
    categories: { status: 'success', data: categoryValues, error: null },
    retryAccounts: async () => {},
    retryCategories: async () => {},
  }
  const markup = renderToString(createElement(
    AccountCategoryContext.Provider,
    { value: accountCategoryValue },
    createElement(AuthContext.Provider, { value: { user: validAuthUser } },
      createElement(FinanceContext.Provider, { value: financeValue }, createElement(SettingsPage))),
  ))
  assert.match(markup, /Primary account/)
  assert.match(markup, /Available to spend/)
  assert.match(markup, /₹6\.5/)
  assert.match(markup, /Income/)
  assert.match(markup, /Expenses/)
  assert.match(markup, /Food/)
})

test('connected API DTO parsers reject malformed auth, CSRF, account, and category responses', async () => {
  const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  const accountId = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
  const validAccount = {
    id: accountId,
    name: 'Primary',
    account_type: 'bank',
    is_default: true,
    opening_balance_paise: 4500,
    opening_balance_as_of: '2026-01-01',
    balance_paise: 4500,
    goal_allocated_paise: 0,
    available_to_spend_paise: 4500,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00+00:00',
  }
  const responseClient = (value) => new ApiClient('http://localhost:8000', async () => jsonResponse(value))

  const missingUserField = new AuthApi(responseClient({ id: userId, email: 'person@example.test' }))
  await assert.rejects(missingUserField.restoreSession(), ApiContractError)
  const invalidNullableUser = new AuthApi(responseClient({ id: userId, email: 'person@example.test', display_name: 7 }))
  await assert.rejects(invalidNullableUser.restoreSession(), ApiContractError)
  const invalidUserId = new AuthApi(responseClient({ id: 'not-a-uuid', email: 'person@example.test', display_name: null }))
  await assert.rejects(invalidUserId.restoreSession(), ApiContractError)
  const nullableUser = new AuthApi(new ApiClient('http://localhost:8000', async (url) => (
    new URL(String(url)).pathname === '/api/auth/me'
      ? jsonResponse({ id: userId, email: 'person@example.test', display_name: null })
      : jsonResponse({ csrf_token: 'csrf-token' })
  )))
  assert.equal((await nullableUser.restoreSession()).display_name, null)

  const missingCsrf = new AuthApi(new ApiClient('http://localhost:8000', async (url) => (
    new URL(String(url)).pathname === '/api/auth/me'
      ? jsonResponse({ id: userId, email: 'person@example.test', display_name: null })
      : jsonResponse({})
  )))
  await assert.rejects(missingCsrf.restoreSession(), ApiContractError)
  const malformedCsrf = new AuthApi(new ApiClient('http://localhost:8000', async (url) => (
    new URL(String(url)).pathname === '/api/auth/me'
      ? jsonResponse({ id: userId, email: 'person@example.test', display_name: null })
      : jsonResponse({ csrf_token: 9 })
  )))
  await assert.rejects(malformedCsrf.restoreSession(), ApiContractError)

  const accountObjectClient = responseClient(validAccount)
  await assert.rejects(new AccountsApi(accountObjectClient).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient([{
    ...validAccount,
    account_type: 'credit_card',
  }])).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient([{
    ...validAccount,
    balance_paise: Number.MAX_SAFE_INTEGER + 1,
  }])).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient([{
    ...validAccount,
    balance_paise: 1.5,
  }])).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient([{
    ...validAccount,
    opening_balance_as_of: '2026-02-30',
  }])).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient([{
    ...validAccount,
    updated_at: 'not-a-timestamp',
  }])).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient([{
    ...validAccount,
    name: undefined,
  }])).list(), ApiContractError)
  await assert.rejects(new AccountsApi(responseClient(null)).get(accountId), ApiContractError)
  await assert.rejects(new AccountsApi(new ApiClient('http://localhost:8000', async () => (
    new Response(null, { status: 200 })
  ))).get(accountId), ApiContractError)

  await assert.rejects(new CategoriesApi(responseClient({ categories: [] })).listActive(), ApiContractError)
  await assert.rejects(new CategoriesApi(responseClient([
    { id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', name: 'Food', transaction_type: 'transfer' },
  ])).listActive(), ApiContractError)
})

test('login and registration establish a session, load CSRF, and logout clears it', async () => {
  const user = { id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', email: 'new@example.test', display_name: 'New User' }
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    const path = new URL(String(url)).pathname
    calls.push({ path, options })
    if (path === '/api/auth/login' || path === '/api/auth/register') return jsonResponse(user)
    if (path === '/api/auth/csrf') return jsonResponse({ csrf_token: 'csrf-from-backend' })
    if (path === '/api/auth/me') return jsonResponse(user)
    if (path === '/api/auth/logout') return new Response(null, { status: 204 })
    throw new Error(`Unexpected path ${path}`)
  })
  const auth = new AuthApi(client)

  assert.deepEqual(await auth.login({ email: user.email, password: 'a password never logged' }), user)
  assert.deepEqual(calls.slice(0, 3).map((call) => call.path), [
    '/api/auth/login', '/api/auth/csrf', '/api/auth/me',
  ])
  assert.equal(calls[0].options.headers.get('Content-Type'), 'application/json')
  assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false)

  calls.length = 0
  assert.deepEqual(await auth.register({
    email: user.email,
    password: 'another password never logged',
    display_name: user.display_name,
    account_type: 'bank',
  }), user)
  assert.deepEqual(calls.slice(0, 3).map((call) => call.path), [
    '/api/auth/register', '/api/auth/csrf', '/api/auth/me',
  ])
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    email: user.email,
    password: 'another password never logged',
    display_name: user.display_name,
    account_type: 'bank',
  })

  await auth.logout()
  const logoutCall = calls.at(-1)
  assert.equal(logoutCall.path, '/api/auth/logout')
  assert.equal(logoutCall.options.headers.get('X-CSRF-Token'), 'csrf-from-backend')
  assert.equal(logoutCall.options.body, undefined)
})

test('login and registration preserve backend failures, and successful logout clears CSRF state', async () => {
  let csrfRequests = 0
  const client = new ApiClient('http://localhost:8000', async (url) => {
    const path = new URL(String(url)).pathname
    if (path === '/api/auth/login') return jsonResponse({ detail: 'Invalid email or password' }, 401)
    if (path === '/api/auth/register') return jsonResponse({ detail: 'Email already registered' }, 409)
    if (path === '/api/auth/csrf') {
      csrfRequests += 1
      return jsonResponse({ csrf_token: `csrf-${csrfRequests}` })
    }
    if (path === '/api/auth/logout') return new Response(null, { status: 204 })
    throw new Error(`Unexpected path ${path}`)
  })
  const auth = new AuthApi(client)

  await assert.rejects(
    auth.login({ email: 'person@example.test', password: 'incorrect password' }),
    (error) => error instanceof ApiError && error.status === 401,
  )
  await assert.rejects(
    auth.register({
      email: 'person@example.test',
      password: 'a sufficiently long registration password',
      display_name: 'Person',
      account_type: 'bank',
    }),
    (error) => error instanceof ApiError && error.status === 409,
  )

  await auth.logout()
  await auth.logout()
  assert.equal(csrfRequests, 2, 'the second logout fetches a fresh CSRF token after the first cleared it')
})

test('failed logout preserves the CSRF state and reports the server failure', async () => {
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ path: new URL(String(url)).pathname, options })
    if (calls.at(-1).path === '/api/auth/logout') {
      return jsonResponse({ detail: 'Logout unavailable' }, 500)
    }
    return jsonResponse({ ok: true })
  })
  const auth = new AuthApi(client)
  client.setCsrfToken('session-csrf')

  await assert.rejects(auth.logout(), (error) => error instanceof ApiError && error.status === 500)
  await client.request('/api/accounts/account-id', { method: 'PATCH', body: { name: 'Check token remains' } })
  assert.equal(calls.at(-1).options.headers.get('X-CSRF-Token'), 'session-csrf')
})

for (const operation of ['login', 'register']) {
  test(`mounted StrictMode provider keeps ${operation} rejections unauthenticated`, async () => {
    const rejected = operation === 'login'
      ? { status: 401, body: { detail: 'Invalid email or password' } }
      : { status: 409, body: { detail: 'An account with this email already exists' } }
    const { service, calls } = scriptedAuthApi({
      'GET /api/auth/me': [{ status: 401 }],
      [`POST /api/auth/${operation}`]: [rejected],
    })
    const mounted = await startSignedOutProvider(service)
    try {
      await act(async () => {
        if (operation === 'login') await mounted.auth.login('person@example.test', 'rejected password')
        else await mounted.auth.register({
          email: 'person@example.test', password: 'valid rejected password',
          display_name: 'Person', account_type: 'bank',
        })
      })
      assert.equal(mounted.status, 'unauthenticated')
      assert.match(mounted.text, operation === 'login' ? /Invalid email or password/ : /already exists/)
      assert.equal(calls.filter((call) => call.key === `POST /api/auth/${operation}`).length, 1)
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  })

  test(`mounted StrictMode provider reconciles ${operation} after CSRF finalization failure`, async () => {
    const { service, calls } = scriptedAuthApi({
      'GET /api/auth/me': [{ status: 401 }, { body: validAuthUser }],
      [`POST /api/auth/${operation}`]: [{ body: { accepted: true } }],
      'GET /api/auth/csrf': [{ status: 500, body: { detail: 'Temporary failure' } }, { body: { csrf_token: 'reconciled-csrf' } }],
    })
    const mounted = await startSignedOutProvider(service)
    try {
      await act(async () => {
        if (operation === 'login') await mounted.auth.login('person@example.test', 'valid password')
        else await mounted.auth.register({
          email: 'person@example.test', password: 'valid registration password',
          display_name: 'Person', account_type: 'bank',
        })
      })
      assert.equal(mounted.status, 'reconciliation-error')
      assert.match(mounted.text, /server accepted your request/i)
      assert.match(mounted.text, /do not submit your credentials again/i)
      const initialIdentity = mounted.auth.sessionIdentity

      await act(async () => mounted.auth.retrySessionReconciliation())
      assert.equal(mounted.status, 'authenticated')
      assert.equal(mounted.auth.user.id, validAuthUser.id)
      assert.notStrictEqual(mounted.auth.sessionIdentity, initialIdentity)
      assert.equal(calls.filter((call) => call.key === `POST /api/auth/${operation}`).length, 1)
      assert.deepEqual(calls.map((call) => call.key), [
        'GET /api/auth/me', `POST /api/auth/${operation}`, 'GET /api/auth/csrf',
        'GET /api/auth/me', 'GET /api/auth/csrf',
      ])
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  })

  test(`mounted StrictMode provider reconciles ${operation} after /me finalization failure`, async () => {
    const { service, calls } = scriptedAuthApi({
      'GET /api/auth/me': [{ status: 401 }, { status: 500, body: { detail: 'Temporary failure' } }, { body: validAuthUser }],
      [`POST /api/auth/${operation}`]: [{ body: { accepted: true } }],
      'GET /api/auth/csrf': [{ body: { csrf_token: 'initial-csrf' } }, { body: { csrf_token: 'reconciled-csrf' } }],
    })
    const mounted = await startSignedOutProvider(service)
    try {
      await act(async () => {
        if (operation === 'login') await mounted.auth.login('person@example.test', 'valid password')
        else await mounted.auth.register({
          email: 'person@example.test', password: 'valid registration password',
          display_name: 'Person', account_type: 'bank',
        })
      })
      assert.equal(mounted.status, 'reconciliation-error')
      await act(async () => mounted.auth.retrySessionReconciliation())
      assert.equal(mounted.status, 'authenticated')
      assert.equal(calls.filter((call) => call.key === `POST /api/auth/${operation}`).length, 1)
      assert.equal(calls.filter((call) => call.key === 'GET /api/auth/me').length, 3)
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  })

  test(`mounted StrictMode provider reconciles ${operation} after a network finalization failure`, async () => {
    const responses = operation === 'login'
      ? {
        'GET /api/auth/me': [{ status: 401 }, { body: validAuthUser }],
        'POST /api/auth/login': [{ body: { accepted: true } }],
        'GET /api/auth/csrf': [new TypeError('offline'), { body: { csrf_token: 'reconciled-csrf' } }],
      }
      : {
        'GET /api/auth/me': [{ status: 401 }, new TypeError('offline'), { body: validAuthUser }],
        'POST /api/auth/register': [{ body: { accepted: true } }],
        'GET /api/auth/csrf': [{ body: { csrf_token: 'initial-csrf' } }, { body: { csrf_token: 'reconciled-csrf' } }],
      }
    const { service, calls } = scriptedAuthApi(responses)
    const mounted = await startSignedOutProvider(service)
    try {
      await act(async () => {
        if (operation === 'login') await mounted.auth.login('person@example.test', 'valid password')
        else await mounted.auth.register({
          email: 'person@example.test', password: 'valid registration password',
          display_name: 'Person', account_type: 'bank',
        })
      })
      assert.equal(mounted.status, 'reconciliation-error')
      await act(async () => mounted.auth.retrySessionReconciliation())
      assert.equal(mounted.status, 'authenticated')
      assert.equal(calls.filter((call) => call.key === `POST /api/auth/${operation}`).length, 1)
    } finally {
      await mounted.unmount()
      mounted.close()
    }
  })
}

test('mounted provider keeps reconciliation errors through repeated retry failures and blocks credential resubmission', async () => {
  const { service, calls } = scriptedAuthApi({
    'GET /api/auth/me': [{ status: 401 }, { status: 500 }, { status: 503 }, { body: validAuthUser }, { body: validAuthUser }],
    'POST /api/auth/login': [{ body: { accepted: true } }],
    'GET /api/auth/csrf': [{ status: 500 }, { status: 500 }, { body: { csrf_token: 'fresh-csrf' } }],
  })
  const mounted = await startSignedOutProvider(service)
  try {
    await act(async () => mounted.auth.login('person@example.test', 'valid password'))
    assert.equal(mounted.status, 'reconciliation-error')
    await act(async () => {
      await mounted.auth.login('person@example.test', 'do not resend')
      await mounted.auth.register({
        email: 'person@example.test', password: 'do not resend registration',
        display_name: 'Person', account_type: 'bank',
      })
    })
    assert.equal(calls.filter((call) => call.key === 'POST /api/auth/login').length, 1)
    assert.equal(calls.filter((call) => call.key === 'POST /api/auth/register').length, 0)

    await act(async () => mounted.auth.retrySessionReconciliation())
    assert.equal(mounted.status, 'reconciliation-error')
    await act(async () => mounted.auth.retrySessionReconciliation())
    assert.equal(mounted.status, 'reconciliation-error')
    await act(async () => mounted.auth.retrySessionReconciliation())
    assert.equal(mounted.status, 'reconciliation-error')
    await act(async () => mounted.auth.retrySessionReconciliation())
    assert.equal(mounted.status, 'authenticated')
    assert.equal(calls.filter((call) => call.key === 'POST /api/auth/login').length, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted provider clears CSRF and returns to signed out only after reconciliation confirms 401', async () => {
  const { service, client, calls } = scriptedAuthApi({
    'GET /api/auth/me': [{ status: 401 }, { status: 401 }],
    'POST /api/auth/register': [{ body: { accepted: true } }],
    'GET /api/auth/csrf': [{ status: 500 }],
  })
  const mounted = await startSignedOutProvider(service)
  try {
    await act(async () => mounted.auth.register({
      email: 'person@example.test', password: 'valid registration password',
      display_name: 'Person', account_type: 'bank',
    }))
    assert.equal(mounted.status, 'reconciliation-error')
    client.setCsrfToken('stale-csrf')
    await act(async () => mounted.auth.retrySessionReconciliation())
    assert.equal(mounted.status, 'unauthenticated')
    assert.equal(client.hasCsrfToken(), false)
    assert.equal(calls.filter((call) => call.key === 'POST /api/auth/register').length, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted provider routes restore retries through reconciliation and accepts credentials after confirmed 401', async () => {
  const { service, calls } = scriptedAuthApi({
    'GET /api/auth/me': [{ status: 401 }, { status: 401 }, { body: validAuthUser }],
    'POST /api/auth/register': [{ body: { accepted: true } }],
    'POST /api/auth/login': [{ body: { accepted: true } }],
    'GET /api/auth/csrf': [{ status: 500 }, { body: { csrf_token: 'login-csrf' } }],
  })
  const mounted = await startSignedOutProvider(service)
  try {
    await act(async () => mounted.auth.register({
      email: 'person@example.test', password: 'valid registration password',
      display_name: 'Person', account_type: 'bank',
    }))
    assert.equal(mounted.status, 'reconciliation-error')

    await act(async () => mounted.auth.retrySessionRestore())
    assert.equal(mounted.status, 'unauthenticated')
    await act(async () => mounted.auth.login('person@example.test', 'valid password'))
    assert.equal(mounted.status, 'authenticated')
    assert.equal(calls.filter((call) => call.key === 'POST /api/auth/register').length, 1)
    assert.equal(calls.filter((call) => call.key === 'POST /api/auth/login').length, 1)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted provider rejects logout while reconciliation is active without superseding its recovery', async () => {
  let rejectRestore
  let logoutCalls = 0
  let reconciliationStarted = false
  const service = {
    restoreSession: async () => {
      if (!reconciliationStarted) return null
      if (rejectRestore === undefined) return new Promise((_resolve, reject) => { rejectRestore = reject })
      return validAuthUser
    },
    login: async () => { throw new AuthFinalizationError() },
    register: async () => { throw new Error('unused') },
    logout: async () => { logoutCalls += 1; throw new Error('logout should not run') },
  }
  const mounted = await startSignedOutProvider(service)
  try {
    await act(async () => mounted.auth.login('person@example.test', 'valid password'))
    reconciliationStarted = true
    let retry
    await act(async () => { retry = mounted.auth.retrySessionReconciliation() })
    assert.equal(mounted.status, 'reconciling')

    await act(async () => mounted.auth.logout())
    assert.equal(logoutCalls, 0)
    assert.equal(mounted.status, 'reconciling')

    rejectRestore(new Error('temporary restore failure'))
    await act(async () => retry)
    assert.equal(mounted.status, 'reconciliation-error')
    assert.match(mounted.text, /server accepted your request/i)

    await act(async () => mounted.auth.retrySessionReconciliation())
    assert.equal(mounted.status, 'authenticated')
    assert.equal(logoutCalls, 0)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted provider does not let logout supersede an active reconciliation', async () => {
  let resolveRestore
  let reconciliationStarted = false
  let logoutCalls = 0
  const service = {
    restoreSession: async () => reconciliationStarted
      ? new Promise((resolve) => { resolveRestore = resolve })
      : null,
    login: async () => { throw new AuthFinalizationError() },
    register: async () => { throw new Error('unused') },
    logout: async () => { logoutCalls += 1 },
  }
  const mounted = await startSignedOutProvider(service)
  try {
    await act(async () => mounted.auth.login('person@example.test', 'valid password'))
    reconciliationStarted = true
    let retry
    await act(async () => { retry = mounted.auth.retrySessionReconciliation() })
    assert.equal(mounted.status, 'reconciling')
    await act(async () => mounted.auth.logout())
    assert.equal(logoutCalls, 0)
    assert.equal(mounted.status, 'reconciling')
    resolveRestore(validAuthUser)
    await act(async () => retry)
    assert.equal(mounted.status, 'authenticated')
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('mounted provider ignores a stale logout failure after a newer session restore', async () => {
  let rejectLogout
  const service = {
    restoreSession: async () => validAuthUser,
    login: async () => validAuthUser,
    register: async () => validAuthUser,
    logout: async () => new Promise((_resolve, reject) => { rejectLogout = reject }),
  }
  const mounted = await mountAuthProvider(service)
  try {
    await mounted.flush()
    assert.equal(mounted.status, 'authenticated')
    const oldIdentity = mounted.auth.sessionIdentity

    let logout
    await act(async () => { logout = mounted.auth.logout() })
    assert.equal(mounted.auth.isLoggingOut, true)

    await act(async () => mounted.auth.retrySessionRestore())
    assert.equal(mounted.status, 'authenticated')
    assert.notStrictEqual(mounted.auth.sessionIdentity, oldIdentity)
    assert.equal(mounted.auth.isLoggingOut, false)

    rejectLogout(new Error('stale logout failure'))
    await act(async () => logout)
    assert.equal(mounted.status, 'authenticated')
    assert.equal(mounted.auth.user.id, validAuthUser.id)
    assert.equal(mounted.auth.authError, null)
  } finally {
    await mounted.unmount()
    mounted.close()
  }
})

test('session gate explains accepted requests and offers reconciliation retry', () => {
  const contextValue = {
    status: 'reconciliation-error', user: null, sessionIdentity: null,
    authError: 'The server accepted your request, but session verification failed.',
    isSubmitting: false, isLoggingOut: false,
    retrySessionRestore: async () => {}, retrySessionReconciliation: async () => {},
    login: async () => {}, register: async () => {}, logout: async () => {}, clearAuthError: () => {},
  }
  const markup = renderToString(createElement(
    AuthContext.Provider,
    { value: contextValue },
    createElement(SessionGate),
  ))
  assert.match(markup, /Your request was accepted/)
  assert.match(markup, /Retry session verification/)
  assert.doesNotMatch(markup, /Invalid email or password/)
  assert.doesNotMatch(markup, /Create your account/)
})

test('authenticated identity surfaces ignore demo profiles and expose no pretend profile save', async () => {
  const { AppSidebar } = await server.ssrLoadModule('/src/components/layout/Sidebar.tsx')
  const { SidebarProvider } = await server.ssrLoadModule('/src/components/ui/sidebar.tsx')
  const { TooltipProvider } = await server.ssrLoadModule('/src/components/ui/tooltip.tsx')
  const { AssistantPage } = await server.ssrLoadModule('/src/pages/AssistantPage.tsx')
  const financeValue = {
    snapshot: new MockFinanceRepository().getSnapshot(),
    preferences: { currency: 'INR', theme: 'light', budgetAlerts: true, weeklySummary: false },
    updatePreferences() {},
    updateProfile() { assert.fail('Authenticated identity must never be saved to the mock repository') },
  }
  const accountValue = {
    accounts: { status: 'success', data: [], error: null },
    categories: { status: 'success', data: [], error: null },
  }
  for (const user of [validAuthUser, { ...validAuthUser, email: 'other@example.test', display_name: null }, null,
    { ...validAuthUser, display_name: 'Alex Morgan', email: 'server-identity@example.test' }]) {
    const markup = renderToString(createElement(AuthContext.Provider, { value: { user } },
      createElement(FinanceContext.Provider, { value: financeValue },
        createElement(AccountCategoryContext.Provider, { value: accountValue },
          createElement(TooltipProvider, null, createElement(SidebarProvider, null,
            createElement(AppSidebar, { activePage: 'Settings', onNavigate() {} }),
            createElement(SettingsPage),
            createElement(AssistantPage, { messages: [], isTyping: false, onSend() {}, onClear() {} }),
            createElement(DashboardContext.Provider, { value: { summary: { status: 'success', data: parseDashboardSummaryDto(validDashboardDto()), error: null }, retry: async () => {} } },
              createElement(DashboardPage, { onNavigate() {} })),
          )),
        ),
      ),
    ))
    const dom = new JSDOM(markup)
    try {
      assert.equal(dom.window.document.querySelector('#profile-name').value, user?.display_name ?? '')
      assert.equal(dom.window.document.querySelector('#profile-email').value, user?.email ?? '')
      assert.equal(dom.window.document.querySelector('#profile-name').readOnly, true)
      assert.equal(dom.window.document.querySelector('#profile-email').readOnly, true)
      assert.match(markup, /Profile editing is not available yet/)
      const firstName = user?.display_name?.split(' ')[0] || 'there'
      assert.ok(dom.window.document.body.textContent.includes(`Hi ${firstName}`))
      assert.ok(dom.window.document.body.textContent.includes(`Good to see you, ${firstName}`))
      const sidebar = dom.window.document.querySelector('[data-slot="sidebar-header"]')
      assert.ok(sidebar.textContent.includes(user?.display_name || user?.email || 'Your account'))
      if (user) assert.ok(sidebar.textContent.includes(user.email), 'Sidebar identifies the actual signed-in account')
      if (user?.display_name !== 'Alex Morgan') assert.doesNotMatch(markup, /Alex Morgan/)
      assert.doesNotMatch(markup, /alex\.?morgan@example\.com|Save profile|profile-occupation/)
    } finally { dom.window.close() }
  }
})

test('Settings follows restored backend identity through a new session and logout', async () => {
  const { service, calls } = browserAuthApi({
    'GET /api/auth/me': [
      { body: validAuthUser },
      { body: { ...validAuthUser, id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', email: 'second@example.test', display_name: 'Second User' } },
      { body: { ...validAuthUser, email: 'login@example.test', display_name: 'Login User' } },
    ],
    'GET /api/auth/csrf': [{ body: { csrf_token: 'first' } }, { body: { csrf_token: 'second' } }, { body: { csrf_token: 'third' } }],
    'POST /api/auth/logout': [{ body: {} }],
    'POST /api/auth/login': [{ body: {} }],
  })
  const financeValue = {
    snapshot: new MockFinanceRepository().getSnapshot(),
    preferences: { currency: 'INR', theme: 'light', budgetAlerts: true, weeklySummary: false },
    updatePreferences() {},
  }
  const children = createElement(FinanceContext.Provider, { value: financeValue },
    createElement(AccountCategoryContext.Provider, { value: {
      accounts: { status: 'success', data: [], error: null },
      categories: { status: 'success', data: [], error: null },
    } }, createElement(SettingsPage)),
  )
  const mounted = await mountAuthProvider(service, undefined, children)
  try {
    assert.equal(document.querySelector('#profile-name').value, 'Person')
    assert.equal(document.querySelector('#profile-email').value, validAuthUser.email)
    await act(async () => mounted.auth.retrySessionRestore())
    assert.equal(document.querySelector('#profile-name').value, 'Second User')
    assert.equal(document.querySelector('#profile-email').value, 'second@example.test')
    await act(async () => mounted.auth.logout())
    assert.equal(document.querySelector('#profile-name').value, '')
    assert.equal(document.querySelector('#profile-email').value, '')
    assert.doesNotMatch(mounted.text, /Alex Morgan|Second User|Save profile/)
    await act(async () => mounted.auth.login('login@example.test', 'test-only password'))
    assert.equal(document.querySelector('#profile-name').value, 'Login User')
    assert.equal(document.querySelector('#profile-email').value, 'login@example.test')
    assert.equal(calls.filter((call) => call.key === 'GET /api/auth/me').length, 3)
  } finally { await mounted.unmount(); mounted.close() }
})

test('authentication UI renders pending and backend error states', () => {
  const contextValue = {
    status: 'unauthenticated',
    user: null,
    sessionIdentity: null,
    authError: 'The account could not be created.',
    isSubmitting: true,
    isLoggingOut: false,
    retrySessionRestore: async () => {},
    retrySessionReconciliation: async () => {},
    login: async () => {},
    register: async () => {},
    logout: async () => {},
    clearAuthError: () => {},
  }
  const markup = renderToString(createElement(
    AuthContext.Provider,
    { value: contextValue },
    createElement(AuthPage),
  ))
  assert.match(markup, /role="alert"/)
  assert.match(markup, /The account could not be created\./)
  assert.match(markup, /disabled=""/)
  assert.match(markup, /Signing in…/)
})

test('app shows session restoration before mounting private finance pages', () => {
  const markup = renderToString(createElement(App))
  assert.match(markup, /Restoring your secure session/)
  assert.doesNotMatch(markup, /Dashboard|Alex Morgan|Transactions/)
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

const validBudgetDto = (overrides = {}) => ({
  id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', month_start: '2026-11-01',
  category_id: null, category_name: null, limit_paise: 100000,
  actual_spending_paise: '900719925474099199', remaining_paise: '-900719925473999199',
  percent_used_basis_points: '900719925474099199',
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z', ...overrides,
})
const validGoalDto = (overrides = {}) => ({
  id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', name: 'Overfunded goal', description: null,
  target_paise: 100, target_date: null, allocated_paise: 150, remaining_target_paise: -50,
  account_allocations: [{ account_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', allocated_paise: 150 }],
  created_at: '2026-11-01T00:00:00Z', updated_at: '2026-11-01T00:00:00Z', ...overrides,
})

async function mountFinanceApiProvider(kind, service, { sessionGeneration = 1, retryAccounts = async () => {}, strictMode = false, children = null } = {}) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost/', pretendToBeVisual: true })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, HTMLElement: dom.window.HTMLElement, Element: dom.window.Element, Node: dom.window.Node, MutationObserver: dom.window.MutationObserver, IS_REACT_ACT_ENVIRONMENT: true })) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  }
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(dom.window.document.getElementById('root'))
  const context = kind === 'budget' ? BudgetsContext : SavingsGoalsContext
  let current
  function Probe() { current = useContext(context); return children }
  const accountValue = {
    accounts: { status: 'success', data: [], error: null }, categories: { status: 'success', data: [], error: null },
    retryAccounts, retryCategories: async () => {},
  }
  const render = (generation = sessionGeneration) => {
    const Provider = kind === 'budget' ? BudgetsProvider : SavingsGoalsProvider
    const provider = createElement(Provider, { sessionGeneration: generation, onUnauthorized: async () => {}, service }, createElement(Probe))
    const tree = kind === 'budget' ? provider : createElement(AccountCategoryContextForGoals.Provider, { value: accountValue }, provider)
    return strictMode ? createElement(StrictMode, null, tree) : tree
  }
  await act(async () => { root.render(render()); await new Promise((resolve) => setTimeout(resolve, 0)) })
  return {
    get current() { return current },
    get text() { return dom.window.document.body.textContent },
    async rerender(generation) { await act(async () => { root.render(render(generation)); await new Promise((resolve) => setTimeout(resolve, 0)) }) },
    async unmount() { await act(async () => root.unmount()) },
    close() { dom.window.close(); for (const [name, descriptor] of previousGlobals) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name] } },
  }
}

const reportedGoalPage = {
  items: [{
    id: 'c7297daa-bb0b-49c5-b307-77b42bf9afed',
    name: 'Emergency fund',
    description: null,
    target_paise: 2000000,
    target_date: null,
    allocated_paise: 1000000,
    remaining_target_paise: 1000000,
    account_allocations: [{ account_id: '0b4e6081-1661-4cac-98cc-d85e9b5b6261', allocated_paise: 1000000 }],
    created_at: '2026-11-14T19:16:55.191355Z',
    updated_at: '2026-11-14T19:16:55.191355Z',
  }],
  total: 1,
  offset: 0,
  limit: 50,
}

test('reported goals response loads and renders through the HTTP client and StrictMode provider', async () => {
  const { SavingsGoalsPage } = await server.ssrLoadModule('/src/pages/SavingsGoalsPage.tsx')
  const calls = []
  const service = new GoalsApi(new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: String(url), options })
    return jsonResponse(reportedGoalPage)
  }))
  const mounted = await mountFinanceApiProvider('goal', service, { strictMode: true, children: createElement(SavingsGoalsPage) })
  try {
    assert.equal(mounted.current.goals.status, 'success', mounted.current.goals.error)
    assert.deepEqual(mounted.current.goals.data, reportedGoalPage)
    assert.match(mounted.text, /Emergency fund/)
    assert.match(mounted.text, /50\.00% allocated/)
    assert.doesNotMatch(mounted.text, /Could not load savings goals|Loading savings goals/)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].url, 'http://localhost:8000/api/goals?offset=0&limit=50')
    assert.equal(calls[0].options.method, 'GET')
    assert.equal(calls[0].options.credentials, 'include')
    assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false)
    await mounted.rerender(2)
    assert.equal(mounted.current.goals.status, 'success', mounted.current.goals.error)
    assert.equal(calls.length, 2, 'New authentication generation loads its own goal page')
  } finally { await mounted.unmount(); mounted.close() }
})

test('reported goals response recovers after a failed request through explicit StrictMode retry', async () => {
  const { SavingsGoalsPage } = await server.ssrLoadModule('/src/pages/SavingsGoalsPage.tsx')
  let requests = 0
  const service = new GoalsApi(new ApiClient('http://localhost:8000', async () => {
    requests += 1
    if (requests === 1) throw new TypeError('offline')
    return jsonResponse(reportedGoalPage)
  }))
  const mounted = await mountFinanceApiProvider('goal', service, { strictMode: true, children: createElement(SavingsGoalsPage) })
  try {
    assert.equal(mounted.current.goals.status, 'error')
    assert.equal(mounted.current.goals.data, null)
    assert.match(mounted.text, /Unable to reach VibeWealth/)
    assert.doesNotMatch(mounted.text, /Emergency fund/)
    assert.equal(requests, 1)
    await act(async () => mounted.current.retryGoals())
    assert.equal(requests, 2)
    assert.equal(mounted.current.goals.status, 'success', mounted.current.goals.error)
    assert.deepEqual(mounted.current.goals.data, reportedGoalPage)
    assert.match(mounted.text, /Emergency fund/)
    assert.doesNotMatch(mounted.text, /Unable to reach VibeWealth|Could not load savings goals/)
  } finally { await mounted.unmount(); mounted.close() }
})

test('goals API/provider preserve description validation and recover with a real authenticated read', async () => {
  const calls = []
  const missingDescription = validGoalDto()
  delete missingDescription.description
  const responses = [
    jsonResponse({ items: [missingDescription], total: 1, offset: 0, limit: 50 }),
    jsonResponse({ items: [validGoalDto({ description: null })], total: 1, offset: 0, limit: 50 }),
  ]
  const service = new GoalsApi(new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url: String(url), options })
    assert.ok(responses.length)
    return responses.shift()
  }))
  const mounted = await mountFinanceApiProvider('goal', service)
  try {
    assert.equal(mounted.current.goals.status, 'error')
    assert.equal(mounted.current.goals.data, null, 'No sample-goal fallback')
    assert.match(mounted.current.goals.error, /invalid savings goal response/)
    assert.match(mounted.current.goals.error, /backend response contract.*migrations/)
    await act(async () => mounted.current.retryGoals())
    assert.equal(mounted.current.goals.status, 'success')
    assert.equal(mounted.current.goals.data.items[0].description, null)
    assert.equal(calls.length, 2)
    assert.ok(calls.every(({ url, options }) => url === 'http://localhost:8000/api/goals?offset=0&limit=50'
      && options.method === 'GET' && options.credentials === 'include'))
  } finally { await mounted.unmount(); mounted.close() }
})

for (const empty of [false, true]) {
  test(`goal page handles a paginated ${empty ? 'empty' : 'two-goal'} result without a loading error`, async () => {
    const { SavingsGoalsPage } = await server.ssrLoadModule('/src/pages/SavingsGoalsPage.tsx')
    // Only one exact goal was supplied in the report; the second is a test fixture.
    const items = empty ? [] : [reportedGoalPage.items[0], validGoalDto({ name: 'Second savings goal' })]
    const page = { items, total: items.length, offset: 0, limit: 50 }
    const service = new GoalsApi(new ApiClient('http://localhost:8000', async () => jsonResponse(page)))
    const mounted = await mountFinanceApiProvider('goal', service, { strictMode: true, children: createElement(SavingsGoalsPage) })
    try {
      assert.equal(mounted.current.goals.status, 'success', mounted.current.goals.error)
      assert.deepEqual(mounted.current.goals.data, page)
      if (empty) {
        assert.match(mounted.text, /Give a goal a name/)
        assert.doesNotMatch(mounted.text, /Contribute|Emergency fund/)
      } else {
        assert.match(mounted.text, /Emergency fund/)
        assert.match(mounted.text, /Second savings goal/)
      }
      assert.doesNotMatch(mounted.text, /Could not load savings goals|Loading savings goals/)
    } finally { await mounted.unmount(); mounted.close() }
  })
}

for (const direction of ['contribution', 'withdrawal']) {
  test(`goal ${direction} accepts the backend allocation account summary without posting a transaction`, async () => {
    const goal = validGoalDto()
    const accountId = goal.account_allocations[0].account_id
    const response = {
      entry: {
        id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', goal_id: goal.id, account_id: accountId,
        entry_type: direction, amount_paise: 125, effective_date: '2026-11-14',
        created_at: '2026-11-14T19:16:55.191355Z',
      },
      goal,
      account: { account_id: accountId, balance_paise: 10000, goal_allocated_paise: 150, available_to_spend_paise: 9850 },
    }
    const calls = []
    const client = new ApiClient('http://localhost:8000', async (url, options) => {
      calls.push({ path: new URL(String(url)).pathname, options })
      return jsonResponse(response)
    })
    client.setCsrfToken('allocation-csrf')
    const service = new GoalsApi(client)
    const result = direction === 'contribution'
      ? await service.contribute(goal.id, accountId, 125)
      : await service.withdraw(goal.id, accountId, 125)
    assert.deepEqual(result, response)
    assert.equal(calls.length, 1)
    assert.equal(calls[0].path, `/api/goals/${goal.id}/${direction}s`)
    assert.equal(calls[0].options.method, 'POST')
    assert.equal(calls[0].options.credentials, 'include')
    assert.equal(calls[0].options.headers.get('X-CSRF-Token'), 'allocation-csrf')
    assert.deepEqual(JSON.parse(calls[0].options.body), { account_id: accountId, amount_paise: 125 })
    assert.ok(calls.every(({ path }) => !path.startsWith('/api/transactions')))
    const { parseGoalMoneyMutationDto } = await server.ssrLoadModule('/src/services/api/responseSchemas.ts')
    for (const invalid of [
      { ...response.account, account_id: undefined },
      { ...response.account, balance_paise: '10000' },
      { ...response.account, allocated_paise: 150, goal_allocated_paise: undefined },
      { ...response.account, available_to_spend_paise: 0.5 },
    ]) assert.throws(() => parseGoalMoneyMutationDto({ ...response, account: invalid }), ApiContractError)
  })
}

test('goals server failures retain HTTP status and development guidance without leaking internals', async () => {
  const service = new GoalsApi(new ApiClient('http://localhost:8000', async () => (
    jsonResponse({ detail: 'SQL traceback with private financial values' }, 500)
  )))
  const mounted = await mountFinanceApiProvider('goal', service)
  try {
    assert.equal(mounted.current.goals.status, 'error')
    assert.equal(mounted.current.goals.data, null)
    assert.match(mounted.current.goals.error, /HTTP 500/)
    assert.match(mounted.current.goals.error, /backend logs.*migrations/)
    assert.doesNotMatch(mounted.current.goals.error, /SQL|traceback|private financial values/)
  } finally { await mounted.unmount(); mounted.close() }
})

async function mountGoalMoneyDialog({ accounts, direction = 'add', onSave = async () => {}, accountStatus = 'success', retryAccounts = async () => {} }) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost/', pretendToBeVisual: true })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT', 'requestAnimationFrame', 'cancelAnimationFrame', 'getComputedStyle']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement, Element: dom.window.Element, Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver, IS_REACT_ACT_ENVIRONMENT: true,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    getComputedStyle: dom.window.getComputedStyle.bind(dom.window),
  })) Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(dom.window.document.getElementById('root'))
  const goal = validGoalDto({ account_allocations: accounts.map((account, index) => ({ account_id: account.id, allocated_paise: (index + 1) * 1000 })) })
  const render = (list, status = accountStatus) => createElement(AccountCategoryContextForGoals.Provider, {
    value: { accounts: { status, data: list, error: status === 'error' ? 'Account request failed.' : null }, categories: { status: 'success', data: [], error: null }, retryAccounts, retryCategories: async () => {} },
  }, createElement(GoalMoneyDialog, { open: true, goal, direction, onOpenChange() {}, onSave, isSaving: false }))
  await act(async () => { root.render(render(accounts)); await new Promise((resolve) => setTimeout(resolve, 0)) })
  return {
    document: dom.window.document,
    async rerenderAccounts(list) { await act(async () => { root.render(render(list, 'success')); await new Promise((resolve) => setTimeout(resolve, 0)) }) },
    async rerenderAccountState(status, list = []) { await act(async () => { root.render(render(list, status)); await new Promise((resolve) => setTimeout(resolve, 0)) }) },
    async selectAccount(name) {
      const trigger = dom.window.document.querySelector('#goal-account')
      assert.ok(trigger, 'Expected account selector')
      await act(async () => trigger.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true, cancelable: true })))
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
      const option = [...dom.window.document.querySelectorAll('[role="option"]')].find((item) => item.textContent.includes(name))
      assert.ok(option, `Expected account option containing ${name}`)
      await act(async () => {
        option.dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true, cancelable: true }))
        option.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }))
      })
    },
    selectedAccountText() { return dom.window.document.querySelector('#goal-account')?.textContent ?? '' },
    async setAmount(value) {
      const input = dom.window.document.querySelector('#goal-movement')
      const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), 'value').set
      setter.call(input, value)
      await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })))
    },
    async submit() {
      const form = dom.window.document.querySelector('form')
      await act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
    },
    async unmount() { await act(async () => root.unmount()) },
    close() { dom.window.close(); for (const [name, descriptor] of previousGlobals) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name] } },
  }
}

async function mountDashboardProvider({ service, sessionGeneration = 1, revisions = { transactions: 0, budgets: 0, goals: 0 } }) {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost/', pretendToBeVisual: true })
  const globalNames = ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT', 'requestAnimationFrame', 'cancelAnimationFrame']
  const previousGlobals = new Map(globalNames.map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  for (const [name, value] of Object.entries({
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement, Element: dom.window.Element, Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver, IS_REACT_ACT_ENVIRONMENT: true,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
  })) Object.defineProperty(globalThis, name, { configurable: true, writable: true, value })
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(dom.window.document.getElementById('root'))
  let current
  function Probe() {
    current = useContext(DashboardContext)
    return createElement('output', { 'data-status': current?.summary.status }, current?.summary.data?.cash_flow.net_paise ?? '')
  }
  const render = () => createElement(TransactionsContext.Provider, { value: { mutationRevision: revisions.transactions } },
    createElement(BudgetsContext.Provider, { value: { mutationRevision: revisions.budgets } },
      createElement(SavingsGoalsContext.Provider, { value: { mutationRevision: revisions.goals } },
        createElement(StrictMode, null,
          createElement(DashboardProvider, { sessionGeneration, onUnauthorized: async () => {}, service }, createElement(Probe)),
        ),
      ),
    ),
  )
  await act(async () => { root.render(render()); await new Promise((resolve) => setTimeout(resolve, 0)) })
  return {
    get current() { return current },
    async flush() { await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) }) },
    async update(changes = {}, generation = sessionGeneration) {
      revisions = { ...revisions, ...changes }
      sessionGeneration = generation
      await act(async () => { root.render(render()); await new Promise((resolve) => setTimeout(resolve, 0)) })
    },
    async unmount() { await act(async () => root.unmount()) },
    close() { dom.window.close(); for (const [name, descriptor] of previousGlobals) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete globalThis[name] } },
  }
}

test('budget and savings goal DTO parsers preserve exact aggregate strings and overfunded values', () => {
  const budget = parseBudgetDto(validBudgetDto())
  assert.equal(parseBudgetListDto([validBudgetDto()]).length, 1)
  assert.equal(budget.actual_spending_paise, '900719925474099199')
  assert.equal(typeof budget.actual_spending_paise, 'string')
  assert.equal(typeof budget.remaining_paise, 'string')
  assert.equal(typeof budget.percent_used_basis_points, 'string')
  assert.throws(() => parseBudgetDto(validBudgetDto({ actual_spending_paise: 9007199254740992 })), /invalid budget response/)
  assert.throws(() => parseBudgetDto(validBudgetDto({ remaining_paise: '1.5' })), /invalid budget response/)

  const goal = parseGoalDto(validGoalDto())
  assert.equal(goal.description, null)
  assert.equal(goal.remaining_target_paise, -50)
  assert.deepEqual(parseGoalListDto({ items: [validGoalDto()], total: 1, offset: 0, limit: 50 }).items.length, 1)
  assert.deepEqual(parseGoalEntryListDto({ items: [], total: 51, offset: 50, limit: 50 }).items, [])
  assert.throws(() => parseGoalDto(validGoalDto({ target_paise: Number.MAX_SAFE_INTEGER + 1 })), /invalid savings goal response/)
})

test('large paise aggregates and basis points are formatted without Number conversion', () => {
  assert.equal(formatPaiseExact(900719925474099199n), '₹9,00,71,99,25,47,40,991.99')
  assert.equal(formatPaiseExact(-150n), '-₹1.50')
  assert.equal(formatBasisPoints('12345678901234567890'), '123456789012345678.90')
})

test('budget month helpers use India calendar boundaries and construct date-only month starts', () => {
  const indiaStillFebruary = new Date('2025-02-28T11:00:00.000Z')
  assert.equal(getIndiaMonthKey(indiaStillFebruary), '2025-02')
  assert.equal(getIndiaMonthStart(indiaStillFebruary), '2025-02-01')
  // A UTC+14 device can already be in March while the India financial month is still February.
  assert.equal(new Intl.DateTimeFormat('en-CA', { timeZone: 'Pacific/Kiritimati', year: 'numeric', month: '2-digit' }).format(indiaStillFebruary), '2025-03')

  const indiaAlreadyMarch = new Date('2025-02-28T20:00:00.000Z')
  assert.equal(getIndiaMonthKey(indiaAlreadyMarch), '2025-03')
  assert.equal(indiaAlreadyMarch.toISOString().slice(0, 7), '2025-02')
  assert.equal(getIndiaMonthStart(new Date('2025-06-15T07:00:00.000Z')), '2025-06-01')
  assert.equal(getIndiaMonthKey(new Date('2025-12-31T20:00:00.000Z')), '2026-01')
  assert.equal(getMonthStartDateKey('2026-01'), '2026-01-01')
  assert.throws(() => getMonthStartDateKey('2026-13'), /YYYY-MM/)
})

test('budget and goal API services use the implemented authenticated endpoint contracts', async () => {
  const calls = []
  const client = { request: async (path, options = {}) => {
    calls.push({ path, options })
    if (path.startsWith('/api/budgets') && options.method === 'DELETE') return undefined
    if (path === '/api/budgets' || path.startsWith('/api/budgets?')) return [validBudgetDto()]
    if (path.startsWith('/api/budgets')) return validBudgetDto()
    if (path.endsWith('/contributions') || path.endsWith('/withdrawals')) return { entry: {}, goal: {}, account: {} }
    if (path.endsWith('/entries?offset=0&limit=50')) return { items: [], total: 0, offset: 0, limit: 50 }
    if (path === '/api/goals?offset=0&limit=50') return { items: [validGoalDto()], total: 1, offset: 0, limit: 50 }
    if (options.method === 'DELETE') return undefined
    return validGoalDto()
  } }
  const budgets = new BudgetsApi(client)
  await budgets.list('2026-11-01')
  await budgets.create({ month_start: '2026-11-01', category_id: null, limit_paise: 100 })
  await budgets.update(validBudgetDto().id, { limit_paise: 200 })
  await budgets.delete(validBudgetDto().id)
  assert.equal(calls[0].path, '/api/budgets?month_start=2026-11-01')
  assert.equal(calls[1].options.method, 'POST')
  assert.deepEqual(calls[1].options.body, { month_start: '2026-11-01', category_id: null, limit_paise: 100 })
  assert.equal(calls[2].options.method, 'PATCH')
  assert.equal(calls[3].options.method, 'DELETE')

  calls.length = 0
  const goals = new GoalsApi(client)
  await goals.list(0, 50)
  await goals.create({ name: 'Trip', description: null, target_paise: 100, target_date: null })
  await goals.update(validGoalDto().id, { description: null })
  await goals.entries(validGoalDto().id, 0, 50)
  await goals.contribute(validGoalDto().id, validGoalDto().account_allocations[0].account_id, 25)
  await goals.withdraw(validGoalDto().id, validGoalDto().account_allocations[0].account_id, 10)
  await goals.delete(validGoalDto().id)
  assert.equal(calls[0].path, '/api/goals?offset=0&limit=50')
  assert.equal(calls[3].path, `/api/goals/${validGoalDto().id}/entries?offset=0&limit=50`)
  assert.equal(calls[4].path, `/api/goals/${validGoalDto().id}/contributions`)
  assert.equal(calls[5].path, `/api/goals/${validGoalDto().id}/withdrawals`)
  assert.deepEqual(calls[4].options.body, { account_id: validGoalDto().account_allocations[0].account_id, amount_paise: 25 })
  assert.equal(calls[6].options.method, 'DELETE')
})

test('budget mutation invalidates an older list request before refreshed data is accepted', async () => {
  let resolveInitial
  let listCalls = 0
  const stale = new Promise((resolve) => { resolveInitial = resolve })
  const fresh = validBudgetDto({ actual_spending_paise: '77', remaining_paise: '23', percent_used_basis_points: '7700' })
  const service = {
    list: async () => (++listCalls === 1 ? stale : [fresh]),
    create: async () => validBudgetDto(), update: async () => validBudgetDto(), delete: async () => {},
  }
  const mounted = await mountFinanceApiProvider('budget', service)
  try {
    await act(async () => mounted.current.create({ month_start: '2026-11-01', category_id: null, limit_paise: 100 }))
    assert.equal(listCalls, 2)
    assert.equal(mounted.current.state.data[0].actual_spending_paise, '77')
    await act(async () => { resolveInitial([validBudgetDto({ actual_spending_paise: '999' })]); await new Promise((resolve) => setTimeout(resolve, 0)) })
    assert.equal(mounted.current.state.data[0].actual_spending_paise, '77')
  } finally { await mounted.unmount(); mounted.close() }
})

test('budget provider exposes retryable failures, successful empty state, and resets stale session data', async () => {
  let attempts = 0
  let oldResolve
  const oldLoad = new Promise((resolve) => { oldResolve = resolve })
  const service = {
    list: async () => {
      attempts += 1
      if (attempts === 1) throw new ApiNetworkError()
      if (attempts === 2) return []
      if (attempts === 3) return oldLoad
      return [validBudgetDto({ actual_spending_paise: '42' })]
    },
    create: async () => validBudgetDto(), update: async () => validBudgetDto(), delete: async () => {},
  }
  const mounted = await mountFinanceApiProvider('budget', service)
  try {
    assert.equal(mounted.current.state.status, 'error')
    await act(async () => mounted.current.retry())
    assert.equal(mounted.current.state.status, 'success')
    assert.deepEqual(mounted.current.state.data, [])
    await act(async () => { void mounted.current.retry(); await new Promise((resolve) => setTimeout(resolve, 0)) })
    await mounted.rerender(2)
    assert.equal(mounted.current.state.status, 'success')
    assert.equal(mounted.current.state.data[0].actual_spending_paise, '42')
    await act(async () => { oldResolve([validBudgetDto({ actual_spending_paise: '999' })]); await new Promise((resolve) => setTimeout(resolve, 0)) })
    assert.equal(mounted.current.state.data[0].actual_spending_paise, '42')
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal contribution uses the supplied account, refreshes accounts, and deletion does not withdraw separately', async () => {
  let listCalls = 0
  let accountRefreshes = 0
  const calls = []
  const goal = validGoalDto()
  const service = {
    list: async () => { listCalls += 1; return { items: [goal], total: 1, offset: 0, limit: 50 } },
    create: async () => goal, update: async () => goal,
    delete: async (id) => { calls.push(['delete', id]) },
    entries: async () => ({ items: [], total: 0, offset: 0, limit: 50 }),
    contribute: async (...args) => { calls.push(['contribute', ...args]); return {} },
    withdraw: async (...args) => { calls.push(['withdraw', ...args]); return {} },
  }
  const accountId = goal.account_allocations[0].account_id
  const mounted = await mountFinanceApiProvider('goal', service, { retryAccounts: async () => { accountRefreshes += 1 } })
  try {
    await act(async () => mounted.current.contribute(goal.id, accountId, 250))
    assert.deepEqual(calls[0], ['contribute', goal.id, accountId, 250])
    assert.equal(listCalls, 2)
    assert.equal(accountRefreshes, 1)
    await act(async () => mounted.current.remove(goal.id))
    assert.deepEqual(calls.at(-1), ['delete', goal.id])
    assert.equal(calls.some((call) => call[0] === 'withdraw'), false)
    assert.equal(accountRefreshes, 2)
    assert.equal(listCalls, 3)
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal mutation refresh supersedes a stale in-flight goal list', async () => {
  let resolveOld
  let listCalls = 0
  const oldList = new Promise((resolve) => { resolveOld = resolve })
  const freshGoal = validGoalDto({ name: 'Fresh server state' })
  const service = {
    list: async () => ++listCalls === 1 ? oldList : { items: [freshGoal], total: 1, offset: 0, limit: 50 },
    create: async () => freshGoal, update: async () => freshGoal, delete: async () => {},
    entries: async () => ({ items: [], total: 0, offset: 0, limit: 50 }),
    contribute: async () => ({}), withdraw: async () => ({}),
  }
  const mounted = await mountFinanceApiProvider('goal', service)
  try {
    await act(async () => mounted.current.create({ name: 'Fresh server state', description: null, target_paise: 100, target_date: null }))
    assert.equal(listCalls, 2)
    assert.equal(mounted.current.goals.data.items[0].name, 'Fresh server state')
    await act(async () => { resolveOld({ items: [validGoalDto({ name: 'Stale response' })], total: 1, offset: 0, limit: 50 }); await new Promise((resolve) => setTimeout(resolve, 0)) })
    assert.equal(mounted.current.goals.data.items[0].name, 'Fresh server state')
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal allocation refresh requests the reset ledger page once and ignores the old page result', async () => {
  const goal = validGoalDto()
  let resolveOldPage
  const oldPage = new Promise((resolve) => { resolveOldPage = resolve })
  const entry = (amountPaise) => ({ id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', goal_id: goal.id, account_id: goal.account_allocations[0].account_id, entry_type: 'contribution', amount_paise: amountPaise, effective_date: '2026-11-01', created_at: '2026-11-01T00:00:00Z' })
  const entryRequests = []
  const service = {
    list: async (offset = 0, limit = 50) => ({ items: [goal], total: 1, offset, limit }),
    create: async () => goal, update: async () => goal, delete: async () => {},
    entries: async (id, offset, limit) => {
      entryRequests.push({ id, offset, limit })
      if (offset === 50) return oldPage
      return { items: [entry(offset === 0 && entryRequests.length === 3 ? 2 : 1)], total: 51, offset, limit }
    },
    contribute: async () => ({}), withdraw: async () => ({}),
  }
  const mounted = await mountFinanceApiProvider('goal', service)
  try {
    await act(async () => mounted.current.selectGoal(goal.id))
    await act(async () => mounted.current.setLedgerOffset(50))
    assert.deepEqual(entryRequests.map((request) => request.offset), [0, 50])
    await act(async () => mounted.current.contribute(goal.id, goal.account_allocations[0].account_id, 50))
    assert.deepEqual(entryRequests.map((request) => request.offset), [0, 50, 0])
    assert.equal(mounted.current.ledger.status, 'success')
    assert.equal(mounted.current.ledger.data.offset, 0)
    assert.equal(mounted.current.ledger.data.items[0].amount_paise, 2)
    await act(async () => { resolveOldPage({ items: [entry(999)], total: 51, offset: 50, limit: 50 }); await new Promise((resolve) => setTimeout(resolve, 0)) })
    assert.equal(mounted.current.ledger.data.offset, 0)
    assert.equal(mounted.current.ledger.data.items[0].amount_paise, 2)
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal ledger pagination reloads the selected goal and mutation errors preserve backend detail', async () => {
  const entryCalls = []
  const goal = validGoalDto()
  const service = {
    list: async (offset = 0, limit = 50) => ({ items: [goal], total: 1, offset, limit }),
    create: async () => goal, update: async () => goal, delete: async () => {},
    entries: async (id, offset, limit) => {
      entryCalls.push([id, offset, limit])
      return { items: offset < 101 ? [{ id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', goal_id: id, account_id: goal.account_allocations[0].account_id, entry_type: 'contribution', amount_paise: 1, effective_date: '2026-11-01', created_at: '2026-11-01T00:00:00Z' }] : [], total: 101, offset, limit }
    },
    contribute: async () => { throw new ApiError(409, 'Insufficient available-to-spend balance') },
    withdraw: async () => { throw new ApiError(409, "Withdrawal exceeds this goal's allocation in this account") },
  }
  const mounted = await mountFinanceApiProvider('goal', service)
  try {
    await act(async () => mounted.current.selectGoal(goal.id))
    assert.deepEqual(entryCalls.at(-1), [goal.id, 0, 50])
    await act(async () => mounted.current.setLedgerOffset(50))
    assert.deepEqual(entryCalls.at(-1), [goal.id, 50, 50])
    let contributionFailure
    await act(async () => { contributionFailure = await mounted.current.contribute(goal.id, goal.account_allocations[0].account_id, 10).catch((error) => error) })
    assert.match(contributionFailure.message, /Insufficient available-to-spend balance/)
    assert.equal(mounted.current.mutationError, 'Insufficient available-to-spend balance')
    let withdrawalFailure
    await act(async () => { withdrawalFailure = await mounted.current.withdraw(goal.id, goal.account_allocations[0].account_id, 10).catch((error) => error) })
    assert.match(withdrawalFailure.message, /Withdrawal exceeds this goal's allocation in this account/)
  } finally { await mounted.unmount(); mounted.close() }
})

const secondaryGoalAccount = () => validAccountDto({ id: 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', name: 'Second account', is_default: false, available_to_spend_paise: 2000 })
const tertiaryGoalAccount = () => validAccountDto({ id: 'ffffffff-ffff-4fff-8fff-ffffffffffff', name: 'Third account', is_default: false, available_to_spend_paise: 3000 })

async function mountSavingsGoalsFlow({ accountFailure = false, allocationFailure = false, withdrawalRejection = false, deletionRejection = false, malformedAllocation = false, goalsRefreshFailure = false, accountsRefreshFailure = false, holdMutations = false } = {}) {
  const { SavingsGoalsPage } = await server.ssrLoadModule('/src/pages/SavingsGoalsPage.tsx')
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true })
  const values = {
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement, Element: dom.window.Element, Node: dom.window.Node,
    MutationObserver: dom.window.MutationObserver, IS_REACT_ACT_ENVIRONMENT: true,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    getComputedStyle: dom.window.getComputedStyle.bind(dom.window),
  }
  const previous = new Map(Object.keys(values).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  let goals = [structuredClone(reportedGoalPage.items[0])]
  const account = validAccountDto({ id: goals[0].account_allocations[0].account_id, name: 'Allocation account', balance_paise: 3000000, goal_allocated_paise: 1000000, available_to_spend_paise: 2000000 })
  let accountReads = 0
  let commits = 0
  let releaseMutation
  const mutationGate = new Promise((resolve) => { releaseMutation = resolve })
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    const parsed = new URL(String(url))
    calls.push({ path: parsed.pathname, url: parsed.href, options })
    if (parsed.pathname === '/api/accounts') {
      if (++accountReads === 1 && accountFailure) throw new TypeError('offline')
      if (commits && accountsRefreshFailure) return jsonResponse({ detail: 'Refresh unavailable' }, 500)
      return jsonResponse([account])
    }
    if (parsed.pathname === '/api/categories') return jsonResponse([])
    if (parsed.pathname === '/api/goals' && options.method === 'GET') {
      if (commits && goalsRefreshFailure) return jsonResponse({ detail: 'Refresh unavailable' }, 500)
      return jsonResponse({ items: goals, total: goals.length, offset: 0, limit: 50 })
    }
    if (options.method === 'DELETE') {
      const goal = goals.find((item) => parsed.pathname === `/api/goals/${item.id}`)
      assert.ok(goal)
      if (deletionRejection) return jsonResponse({ detail: 'Goal not found' }, 404)
      if (holdMutations) await mutationGate
      account.goal_allocated_paise -= goal.allocated_paise
      account.available_to_spend_paise += goal.allocated_paise
      goals = goals.filter((item) => item.id !== goal.id)
      commits += 1
      return new Response(null, { status: 204 })
    }
    if (parsed.pathname === '/api/goals' && options.method === 'POST') {
      const input = JSON.parse(options.body)
      const goal = validGoalDto({ ...input, allocated_paise: 0, remaining_target_paise: input.target_paise, account_allocations: [] })
      goals = [...goals, goal]
      return jsonResponse(goal, 201)
    }
    const withdrawal = parsed.pathname.endsWith('/withdrawals')
    const goal = goals.find((item) => parsed.pathname === `/api/goals/${item.id}/${withdrawal ? 'withdrawals' : 'contributions'}`)
    assert.ok(goal, `Unexpected request ${options.method} ${parsed.pathname}`)
    if (withdrawal && withdrawalRejection) return jsonResponse({ detail: "Withdrawal exceeds this goal's allocation in this account" }, 409)
    if (holdMutations) await mutationGate
    const input = JSON.parse(options.body)
    const delta = withdrawal ? -input.amount_paise : input.amount_paise
    goal.allocated_paise += delta
    goal.remaining_target_paise -= delta
    goal.account_allocations = [{ account_id: input.account_id, allocated_paise: goal.allocated_paise }]
    account.goal_allocated_paise += delta
    account.available_to_spend_paise -= delta
    commits += 1
    if (malformedAllocation) return jsonResponse({ entry: {}, goal, account: {} }, 201)
    return jsonResponse({
      entry: { id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', goal_id: goal.id, ...input, entry_type: withdrawal ? 'withdrawal' : 'contribution', effective_date: '2026-11-14', created_at: goal.created_at },
      goal,
      account: { account_id: account.id, balance_paise: account.balance_paise, goal_allocated_paise: account.goal_allocated_paise, available_to_spend_paise: account.available_to_spend_paise },
    }, 201)
  })
  client.setCsrfToken('allocation-csrf')
  const goalsService = new GoalsApi(client)
  if (allocationFailure) goalsService.contribute = async () => { throw new Error('Unexpected allocation failure') }
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(dom.window.document.getElementById('root'))
  const onUnauthorized = async () => { assert.fail('Unexpected unauthorized request') }
  await act(async () => root.render(createElement(StrictMode, null,
    createElement(AccountCategoryProvider, { sessionIdentity: { generation: 1 }, onUnauthorized, accountsService: new AccountsApi(client), categoriesService: new CategoriesApi(client) },
      createElement(SavingsGoalsProvider, { sessionGeneration: 1, onUnauthorized, service: goalsService }, createElement(SavingsGoalsPage)),
    ),
  )))
  const document = dom.window.document
  return {
    document, calls, releaseMutation,
    get commits() { return commits },
    get account() { return account },
    async click(text, scope = document) {
      const button = [...scope.querySelectorAll('button')].find((item) => item.textContent === text)
      assert.ok(button, `Missing button ${text}`)
      assert.equal(button.disabled, false, `${text} must be reachable`)
      await act(async () => button.click())
    },
    async setInput(id, value) {
      const input = document.getElementById(id)
      assert.ok(input, `Missing input ${id}`)
      const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set
      setter.call(input, value)
      await act(async () => input.dispatchEvent(new dom.window.Event('input', { bubbles: true })))
    },
    async deleteGoal(name = 'Emergency fund') {
      const trigger = document.querySelector(`[aria-label="Delete ${name}"]`)
      assert.ok(trigger)
      await act(async () => trigger.click())
      const confirmation = document.querySelector('[role="alertdialog"]')
      assert.ok(confirmation)
      const confirm = [...confirmation.querySelectorAll('button')].find((item) => item.textContent === 'Delete')
      assert.ok(confirm)
      await act(async () => confirm.click())
    },
    async submit() {
      const form = document.querySelector('[role="dialog"] form')
      assert.ok(form)
      await act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
    },
    card(name) { return [...document.querySelectorAll('.goal-card')].find((item) => item.textContent.includes(name)) },
    dialog() { return document.querySelector('[role="dialog"]') },
    async close() {
      await act(async () => root.unmount())
      dom.window.close()
      for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] }
    },
  }
}

test('Savings Goals card contribution flow creates, opens, reopens, saves, and refreshes through shared APIs', async () => {
  const mounted = await mountSavingsGoalsFlow()
  try {
    await mounted.click('New goal')
    await mounted.setInput('goal-name', 'Created goal')
    await mounted.setInput('goal-target', '20000.00')
    await mounted.submit()
    assert.ok(mounted.card('Created goal'))
    const reads = mounted.calls.length
    await mounted.click('Contribute', mounted.card('Created goal'))
    assert.match(mounted.dialog().textContent, /Created goal/)
    assert.equal(mounted.calls.length, reads, 'Opening reads shared state and makes no goals/accounts request')
    await mounted.click('Cancel', mounted.dialog())
    await mounted.click('Contribute', mounted.card('Emergency fund'))
    assert.match(mounted.dialog().textContent, /Emergency fund/)
    await mounted.click('Cancel', mounted.dialog())
    await mounted.click('Contribute', mounted.card('Created goal'))
    await mounted.setInput('goal-movement', '1.25')
    await mounted.submit()
    assert.equal(mounted.dialog(), null)
    assert.match(mounted.card('Created goal').textContent, /₹1\.25/)
    const contribution = mounted.calls.find(({ path }) => path.endsWith('/contributions'))
    assert.ok(contribution)
    assert.equal(contribution.path, `/api/goals/${validGoalDto().id}/contributions`)
    assert.equal(JSON.parse(contribution.options.body).amount_paise, 125)
    assert.equal(contribution.options.headers.get('X-CSRF-Token'), 'allocation-csrf')
    assert.ok(mounted.calls.every(({ path, options }) => !path.startsWith('/api/transactions') && options.credentials === 'include'))
    assert.equal(mounted.calls.filter(({ path }) => path === '/api/accounts').length, 2)
    assert.equal(mounted.calls.filter(({ path, options }) => path === '/api/goals' && options.method === 'GET').length, 3)
    assert.doesNotMatch(mounted.document.body.textContent, /Could not load savings goals/)
  } finally { await mounted.close() }
})

test('Savings Goals card contribution flow can open and genuinely retry failed shared account loading', async () => {
  const mounted = await mountSavingsGoalsFlow({ accountFailure: true })
  try {
    await mounted.click('Contribute', mounted.card('Emergency fund'))
    assert.match(mounted.dialog().textContent, /Unable to reach VibeWealth/)
    assert.match(mounted.dialog().textContent, /Could not load accounts/)
    assert.doesNotMatch(mounted.dialog().textContent, /Could not load savings goals/)
    await mounted.click('Retry accounts', mounted.dialog())
    assert.equal(mounted.calls.filter(({ path }) => path === '/api/accounts').length, 2)
    assert.equal(mounted.document.getElementById('goal-account').disabled, false)
    assert.doesNotMatch(mounted.dialog().textContent, /Unable to reach VibeWealth|Loading accounts|Could not load accounts/)
  } finally { await mounted.close() }
})

test('Savings Goals card contribution flow never labels an allocation exception as goal loading', async () => {
  const mounted = await mountSavingsGoalsFlow({ allocationFailure: true })
  try {
    await mounted.click('Contribute', mounted.card('Emergency fund'))
    await mounted.setInput('goal-movement', '1.25')
    await mounted.submit()
    assert.match(mounted.dialog().textContent, /Could not save goal allocation/)
    assert.doesNotMatch(mounted.dialog().textContent, /Could not load savings goals/)
    await mounted.click('Cancel', mounted.dialog())
    await mounted.click('Contribute', mounted.card('Emergency fund'))
    assert.doesNotMatch(mounted.dialog().textContent, /Could not save goal allocation|Could not load savings goals/)
  } finally { await mounted.close() }
})

test('Savings Goals withdrawal sends authenticated paise, refreshes allocations, and never posts a transaction', async () => {
  const mounted = await mountSavingsGoalsFlow()
  try {
    await mounted.click('Withdraw', mounted.card('Emergency fund'))
    assert.match(mounted.dialog().textContent, /Withdraw from goal/)
    await mounted.setInput('goal-movement', '1.25')
    await mounted.submit()
    assert.equal(mounted.dialog(), null)
    assert.equal(mounted.commits, 1)
    const call = mounted.calls.find(({ path }) => path.endsWith('/withdrawals'))
    assert.equal(call.path, `/api/goals/${reportedGoalPage.items[0].id}/withdrawals`)
    assert.deepEqual(JSON.parse(call.options.body), { account_id: reportedGoalPage.items[0].account_allocations[0].account_id, amount_paise: 125 })
    assert.equal(call.options.credentials, 'include')
    assert.equal(call.options.headers.get('X-CSRF-Token'), 'allocation-csrf')
    assert.match(mounted.card('Emergency fund').textContent, /₹9,998\.75/)
    assert.equal(mounted.account.available_to_spend_paise, 2000125)
    assert.equal(mounted.calls.filter(({ path }) => path === '/api/accounts').length, 2)
    assert.ok(mounted.calls.every(({ path }) => !path.startsWith('/api/transactions')))
  } finally { await mounted.close() }
})

test('Savings Goals withdrawal backend rejection remains retryable and distinct from response parsing', async () => {
  const mounted = await mountSavingsGoalsFlow({ withdrawalRejection: true })
  try {
    await mounted.click('Withdraw', mounted.card('Emergency fund'))
    await mounted.setInput('goal-movement', '1.25')
    await mounted.submit()
    assert.equal(mounted.commits, 0)
    assert.match(mounted.dialog().textContent, /Withdrawal exceeds this goal's allocation in this account/)
    assert.doesNotMatch(mounted.dialog().textContent, /Could not load savings goals|invalid.*response/)
    await mounted.submit()
    assert.equal(mounted.calls.filter(({ path }) => path.endsWith('/withdrawals')).length, 2)
  } finally { await mounted.close() }
})

test('Savings Goals withdrawal invalid successful response reports verification uncertainty without assuming rollback', async () => {
  const mounted = await mountSavingsGoalsFlow({ malformedAllocation: true })
  try {
    await mounted.click('Withdraw', mounted.card('Emergency fund'))
    await mounted.setInput('goal-movement', '1.25')
    await mounted.submit()
    assert.equal(mounted.commits, 1)
    assert.match(mounted.dialog().textContent, /invalid.*response/)
    assert.match(mounted.dialog().textContent, /may have been saved|could not verify|could not be verified/i)
    await mounted.submit()
    assert.equal(mounted.commits, 1, 'An unverifiable success must not allow a duplicate allocation')
    assert.equal(mounted.calls.filter(({ path }) => path.endsWith('/withdrawals')).length, 1)
    assert.equal(mounted.document.getElementById('goal-movement').disabled, true)
  } finally { await mounted.close() }
})

for (const operation of ['withdrawal', 'deletion']) {
  test(`Savings Goals ${operation} succeeds independently of failed post-commit goals/account reads`, async () => {
    const mounted = await mountSavingsGoalsFlow({ goalsRefreshFailure: true, accountsRefreshFailure: true })
    try {
      if (operation === 'withdrawal') {
        await mounted.click('Withdraw', mounted.card('Emergency fund'))
        await mounted.setInput('goal-movement', '1.25')
        await mounted.submit()
      } else await mounted.deleteGoal()
      assert.equal(mounted.commits, 1)
      assert.equal(mounted.dialog(), null)
      assert.equal(mounted.document.querySelector('[role="alertdialog"]'), null)
      assert.match(mounted.document.body.textContent, /server could not complete the request/)
      assert.doesNotMatch(mounted.document.body.textContent, /Could not (?:delete savings goal|save goal allocation)/)
      assert.equal(mounted.calls.filter(({ options }) => options.method === 'POST' || options.method === 'DELETE').length, 1)
    } finally { await mounted.close() }
  })
}

test('Savings Goals Delete action is visible, confirms the chosen goal, and cancel never deletes', async () => {
  const mounted = await mountSavingsGoalsFlow()
  try {
    const card = mounted.card('Emergency fund')
    const action = card.querySelector('[aria-label="Delete Emergency fund"]')
    assert.ok(action)
    assert.equal(action.textContent, 'Delete goal')
    assert.equal(action.disabled, false)
    assert.equal(action.closest('[hidden], [aria-hidden="true"]'), null)
    await mounted.click('Delete goal', card)
    const confirmation = mounted.document.querySelector('[role="alertdialog"]')
    assert.ok(confirmation)
    assert.match(confirmation.textContent, /Emergency fund/)
    assert.match(confirmation.textContent, /allocations are released/)
    assert.equal(mounted.calls.filter(({ options }) => options.method === 'DELETE').length, 0)
    await mounted.click('Cancel', confirmation)
    assert.equal(mounted.document.querySelector('[role="alertdialog"]'), null)
    assert.equal(mounted.calls.filter(({ options }) => options.method === 'DELETE').length, 0)
    assert.ok(mounted.card('Emergency fund'))
    await mounted.deleteGoal()
    assert.equal(mounted.commits, 1)
    assert.equal(mounted.card('Emergency fund'), undefined)
  } finally { await mounted.close() }
})

test('Savings Goals deletion sends one UUID DELETE, removes allocated goal, and refreshes released balances', async () => {
  const mounted = await mountSavingsGoalsFlow()
  try {
    await mounted.deleteGoal()
    assert.equal(mounted.commits, 1)
    assert.equal(mounted.card('Emergency fund'), undefined)
    assert.equal(mounted.document.querySelector('[role="alertdialog"]'), null)
    const writes = mounted.calls.filter(({ options }) => options.method !== 'GET')
    assert.equal(writes.length, 1)
    assert.equal(writes[0].path, `/api/goals/${reportedGoalPage.items[0].id}`)
    assert.equal(writes[0].options.method, 'DELETE')
    assert.equal(writes[0].options.headers.get('X-CSRF-Token'), 'allocation-csrf')
    assert.equal(mounted.account.goal_allocated_paise, 0)
    assert.equal(mounted.account.available_to_spend_paise, 3000000)
    assert.equal(mounted.calls.filter(({ path }) => path === '/api/accounts').length, 2)
    assert.ok(mounted.calls.every(({ path }) => !path.endsWith('/withdrawals') && !path.startsWith('/api/transactions')))
  } finally { await mounted.close() }
})

test('Savings Goals deletion rejection leaves confirmation open and displays a deletion error', async () => {
  const mounted = await mountSavingsGoalsFlow({ deletionRejection: true })
  try {
    await mounted.deleteGoal()
    assert.equal(mounted.commits, 0)
    assert.ok(mounted.card('Emergency fund'))
    assert.ok(mounted.document.querySelector('[role="alertdialog"]'))
    assert.match(mounted.document.body.textContent, /Goal not found/)
    await mounted.click('Delete', mounted.document.querySelector('[role="alertdialog"]'))
    assert.equal(mounted.calls.filter(({ options }) => options.method === 'DELETE').length, 2)
    assert.equal(mounted.commits, 0)
  } finally { await mounted.close() }
})

for (const operation of ['withdrawal', 'deletion']) {
  test(`Savings Goals ${operation} prevents duplicate in-flight submissions`, async () => {
    const mounted = await mountSavingsGoalsFlow({ holdMutations: true })
    try {
      if (operation === 'withdrawal') {
        await mounted.click('Withdraw', mounted.card('Emergency fund'))
        await mounted.setInput('goal-movement', '1.25')
        await mounted.submit()
        await mounted.submit()
      } else {
        await mounted.deleteGoal()
        const button = [...mounted.document.querySelector('[role="alertdialog"]').querySelectorAll('button')].find((item) => item.textContent === 'Working…')
        assert.ok(button)
        assert.equal(button.disabled, true)
        await act(async () => button.click())
      }
      assert.equal(mounted.calls.filter(({ options }) => options.method === 'DELETE' || options.method === 'POST').length, 1)
      await act(async () => mounted.releaseMutation())
      assert.equal(mounted.commits, 1)
    } finally { await mounted.close() }
  })
}

test('goal money dialog distinguishes account loading, retryable failure, and successful empty data', async () => {
  let retries = 0
  const mounted = await mountGoalMoneyDialog({ accounts: [], accountStatus: 'loading', retryAccounts: async () => { retries += 1 } })
  try {
    assert.match(mounted.document.body.textContent, /Loading accounts/)
    assert.doesNotMatch(mounted.document.body.textContent, /No account has available funds/)
    assert.equal(mounted.document.querySelector('#goal-account').disabled, true)
    await mounted.rerenderAccountState('error')
    assert.match(mounted.document.body.textContent, /Account request failed/)
    assert.doesNotMatch(mounted.document.body.textContent, /No account has available funds/)
    const retry = [...mounted.document.querySelectorAll('button')].find((button) => button.textContent === 'Retry accounts')
    assert.ok(retry)
    await act(async () => retry.click())
    assert.equal(retries, 1)
    await mounted.rerenderAccounts([validAccountDto({ name: 'Recovered account' })])
    assert.equal(mounted.document.querySelector('#goal-account').disabled, false)
    await mounted.selectAccount('Recovered account')
    assert.doesNotMatch(mounted.document.body.textContent, /Account request failed|Loading accounts/)
    await mounted.rerenderAccounts([])
    assert.match(mounted.document.body.textContent, /No account has available funds/)
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal money dialog submits integer paise through the real contribution API without a transaction', async () => {
  const account = validAccountDto({ available_to_spend_paise: 10000 })
  const goal = validGoalDto({ account_allocations: [{ account_id: account.id, allocated_paise: 1000 }] })
  const calls = []
  const client = new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ path: new URL(String(url)).pathname, options })
    if (calls.at(-1).path === '/api/accounts') return jsonResponse([account])
    assert.equal(calls.at(-1).path, `/api/goals/${goal.id}/contributions`)
    return jsonResponse({
      entry: { id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', goal_id: goal.id, account_id: account.id,
        entry_type: 'contribution', amount_paise: 125, effective_date: '2026-11-14', created_at: goal.created_at },
      goal,
      account: { account_id: account.id, balance_paise: 10000, goal_allocated_paise: 1125, available_to_spend_paise: 8875 },
    })
  })
  client.setCsrfToken('allocation-csrf')
  const accounts = await new AccountsApi(client).list()
  const service = new GoalsApi(client)
  let saved = false
  const mounted = await mountGoalMoneyDialog({ accounts, onSave: async (accountId, amount) => {
    await service.contribute(goal.id, accountId, amount)
    saved = true
  } })
  try {
    await mounted.selectAccount(account.name)
    await mounted.setAmount('1.25')
    await mounted.submit()
    assert.equal(saved, true)
    assert.deepEqual(calls.map(({ path }) => path), ['/api/accounts', `/api/goals/${goal.id}/contributions`])
    assert.deepEqual(JSON.parse(calls[1].options.body), { account_id: account.id, amount_paise: 125 })
    assert.equal(calls[1].options.headers.get('X-CSRF-Token'), 'allocation-csrf')
    assert.ok(calls.every(({ options }) => options.credentials === 'include'))
    assert.doesNotMatch(mounted.document.body.textContent, /invalid.*response/)
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal money dialog preserves a selected account that remains eligible after account refresh', { concurrency: false }, async () => {
  const primary = validAccountDto({ name: 'First account' })
  const secondary = secondaryGoalAccount()
  const calls = []
  const mounted = await mountGoalMoneyDialog({ accounts: [primary, secondary], onSave: async (...args) => calls.push(args) })
  try {
    await mounted.selectAccount('Second account')
    await mounted.rerenderAccounts([secondary, primary, tertiaryGoalAccount()])
    assert.match(mounted.selectedAccountText(), new RegExp(secondary.id))
    await mounted.setAmount('1.00')
    await mounted.submit()
    assert.deepEqual(calls, [[secondary.id, 100]])
  } finally { await mounted.unmount(); mounted.close() }
})

test('goal money dialog replaces an ineligible selection and refuses to submit with no eligible account', { concurrency: false }, async () => {
  const primary = validAccountDto({ name: 'First account' })
  const secondary = secondaryGoalAccount()
  const tertiary = tertiaryGoalAccount()
  const calls = []
  const mounted = await mountGoalMoneyDialog({ accounts: [primary, secondary], onSave: async (...args) => calls.push(args) })
  try {
    await mounted.selectAccount('Second account')
    assert.match(mounted.selectedAccountText(), new RegExp(secondary.id))
    await mounted.rerenderAccounts([tertiary, primary])
    assert.match(mounted.selectedAccountText(), new RegExp(tertiary.id))
    await mounted.setAmount('1.00')
    await mounted.submit()
    assert.deepEqual(calls, [[tertiary.id, 100]])

    await mounted.rerenderAccounts([])
    assert.match(mounted.document.body.textContent, /No account has available funds/)
    await mounted.submit()
    assert.deepEqual(calls, [[tertiary.id, 100]])
  } finally { await mounted.unmount(); mounted.close() }
})

function validDashboardDto(overrides = {}) {
  return {
    financial_date: '2026-11-14',
    month_start: '2026-11-01',
    month_end_exclusive: '2026-12-01',
    account_totals: {
      account_count: 2,
      balance_paise: '9007199254741991',
      goal_allocated_paise: '5000',
      available_to_spend_paise: '9007199254736991',
    },
    cash_flow: { income_paise: '1000', expenses_paise: '10000', net_paise: '-9000' },
    budgets: [{
      id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', month_start: '2026-11-01', category_id: null, category_name: null,
      limit_paise: 8000, actual_spending_paise: '10000', remaining_paise: '-2000', percent_used_basis_points: '12500',
    }],
    goals: [{
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', name: 'Emergency fund', target_date: null,
      target_paise: 4000, allocated_paise: 5000, remaining_target_paise: -1000,
    }],
    goals_total: 1,
    recent_transactions: {
      items: [{
        id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', account_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        category_id: null, category_name: null, transaction_type: 'expense', amount_paise: 10000,
        description: 'Recent expense', transaction_date: '2026-11-14',
      }],
      total: 1, offset: 0, limit: 4,
    },
    ...overrides,
  }
}

test('dashboard summary API uses the authenticated shared client and validates exact DTO values', async () => {
  const payload = validDashboardDto()
  const parsed = parseDashboardSummaryDto(payload)
  assert.equal(parsed.account_totals.balance_paise, '9007199254741991')
  assert.equal(parsed.cash_flow.net_paise, '-9000')
  assert.equal(parsed.budgets[0].remaining_paise, '-2000')
  assert.equal(parsed.goals[0].remaining_target_paise, -1000)

  const calls = []
  const api = new DashboardApi(new ApiClient('http://localhost:8000', async (url, options) => {
    calls.push({ url, options })
    return jsonResponse(payload)
  }))
  assert.deepEqual(await api.summary(), parsed)
  assert.equal(String(calls[0].url), 'http://localhost:8000/api/dashboard/summary')
  assert.equal(calls[0].options.credentials, 'include')
  assert.equal(calls[0].options.method, 'GET')
  assert.equal(calls[0].options.headers.has('X-CSRF-Token'), false)

  assert.throws(() => parseDashboardSummaryDto(validDashboardDto({
    account_totals: { ...payload.account_totals, balance_paise: Number.MAX_SAFE_INTEGER + 1 },
  })), /invalid dashboard summary/)
  assert.throws(() => parseDashboardSummaryDto(validDashboardDto({
    month_start: '2026-10-01',
  })), /invalid dashboard summary/)
  assert.throws(() => parseDashboardSummaryDto(validDashboardDto({
    cash_flow: { income_paise: '1', expenses_paise: '0', net_paise: '-1' },
  })), /invalid dashboard summary/)
})

test('dashboard renders real aggregate strings, negative cash flow, budget and goal progress, and recent activity', () => {
  const auth = { user: { display_name: 'Asha Rao' } }
  const summary = { status: 'success', data: parseDashboardSummaryDto(validDashboardDto()), error: null }
  const html = renderToString(createElement(AuthContext.Provider, { value: auth },
    createElement(DashboardContext.Provider, { value: { summary, retry: async () => {} } },
      createElement(DashboardPage, { onNavigate() {} }),
    ),
  ))

  assert.match(html.replace(/<!-- -->/g, ''), /Good to see you, Asha/)
  assert.match(html, /₹9,00,71,99,25,47,419\.91/)
  assert.match(html, /-₹90\.00/)
  assert.match(html, /Budget overview/)
  assert.match(html, /Savings goals/)
  assert.match(html, /Recent expense/)
  assert.doesNotMatch(html, /Sample data|mock data/i)

  const empty = validDashboardDto({ budgets: [], goals: [], goals_total: 0, recent_transactions: { items: [], total: 0, offset: 0, limit: 4 } })
  const emptyHtml = renderToString(createElement(AuthContext.Provider, { value: auth },
    createElement(DashboardContext.Provider, { value: { summary: { status: 'success', data: parseDashboardSummaryDto(empty), error: null }, retry: async () => {} } },
      createElement(DashboardPage, { onNavigate() {} }),
    ),
  ))
  assert.match(emptyHtml, /No budgets are set/)
  assert.match(emptyHtml, /Create a savings goal/)
  assert.match(emptyHtml, /No transactions have been recorded/)
})

test('dashboard provider retries failures, refreshes after mutations, and ignores a previous session response', async () => {
  let calls = 0
  let failFirst = true
  const retryService = {
    async summary() {
      calls += 1
      if (failFirst) { failFirst = false; throw new ApiError(503, 'Summary unavailable') }
      return parseDashboardSummaryDto(validDashboardDto())
    },
  }
  const mounted = await mountDashboardProvider({ service: retryService })
  try {
    await mounted.flush()
    assert.equal(mounted.current.summary.status, 'error')
    assert.match(mounted.current.summary.error, /Summary unavailable/)
    await act(async () => mounted.current.retry())
    assert.equal(mounted.current.summary.status, 'success')
    assert.equal(calls, 2)
    await mounted.update({ budgets: 1 })
    await mounted.flush()
    assert.equal(calls, 3)
  } finally { await mounted.unmount(); mounted.close() }

  let resolveOld
  let resolveNew
  let sessionCalls = 0
  const sessionService = {
    summary() {
      sessionCalls += 1
      return new Promise((resolve) => {
        if (sessionCalls === 1) resolveOld = resolve
        else resolveNew = resolve
      })
    },
  }
  const sessionMounted = await mountDashboardProvider({ service: sessionService })
  try {
    await sessionMounted.update({}, 2)
    resolveNew(parseDashboardSummaryDto(validDashboardDto({ cash_flow: { income_paise: '0', expenses_paise: '200', net_paise: '-200' } })))
    await sessionMounted.flush()
    assert.equal(sessionMounted.current.summary.data.cash_flow.net_paise, '-200')
    resolveOld(parseDashboardSummaryDto(validDashboardDto({ cash_flow: { income_paise: '0', expenses_paise: '100', net_paise: '-100' } })))
    await sessionMounted.flush()
    assert.equal(sessionMounted.current.summary.data.cash_flow.net_paise, '-200')
    assert.equal(sessionCalls, 2)
  } finally { await sessionMounted.unmount(); sessionMounted.close() }
})
