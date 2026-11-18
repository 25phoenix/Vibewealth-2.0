import assert from 'node:assert/strict'
import { test } from 'node:test'
import { act, createElement, StrictMode } from 'react'
import { JSDOM } from 'jsdom'
import { createServer } from 'vite'

test('actual App root carries backend Abc identity across all identity surfaces', async () => {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: 'http://localhost:5173/', pretendToBeVisual: true })
  const mediaQueries = new Map()
  dom.window.matchMedia = (media) => {
    if (!mediaQueries.has(media)) mediaQueries.set(media, { matches: false, media, addEventListener() {}, removeEventListener() {} })
    return mediaQueries.get(media)
  }
  const values = {
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    HTMLElement: dom.window.HTMLElement, Element: dom.window.Element, Node: dom.window.Node,
    Event: dom.window.Event, MouseEvent: dom.window.MouseEvent,
    MutationObserver: dom.window.MutationObserver, IS_REACT_ACT_ENVIRONMENT: true,
    localStorage: dom.window.localStorage,
    requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window),
    cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    getComputedStyle: dom.window.getComputedStyle.bind(dom.window),
  }
  const previous = new Map(Object.keys(values).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value })
  let server
  let root
  let client
  let originalFetch
  const calls = []
  // Synthetic email: the user's personal address does not belong in a fixture.
  const backendUser = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', email: 'person@example.test', display_name: 'Abc' }
  const page = { items: [], total: 0, offset: 0, limit: 50 }
  const summary = {
    financial_date: '2026-11-15', month_start: '2026-11-01', month_end_exclusive: '2026-12-01',
    account_totals: { account_count: 0, balance_paise: '0', goal_allocated_paise: '0', available_to_spend_paise: '0' },
    cash_flow: { income_paise: '0', expenses_paise: '0', net_paise: '0' },
    budgets: [], goals: [], goals_total: 0,
    recent_transactions: { items: [], total: 0, offset: 0, limit: 4 },
  }
  const json = (body) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
  try {
    // Node's per-file isolation keeps full-app browser state out of finance tests.
    server = await createServer({ configFile: 'vite.config.ts', server: { middlewareMode: true, hmr: { port: 24679 } }, appType: 'custom' })
    const { apiClient } = await server.ssrLoadModule('/src/services/api/apiClient.ts')
    client = apiClient
    originalFetch = client.fetchImpl
    // Intercept HTTP only; use the actual default AuthApi and provider hierarchy.
    client.fetchImpl = async (url, options) => {
      const path = new URL(String(url)).pathname
      calls.push({ path, url: String(url), options })
      if (path === '/api/auth/me') return json(backendUser)
      if (path === '/api/auth/csrf') return json({ csrf_token: 'test-session-csrf' })
      if (['/api/accounts', '/api/categories', '/api/budgets'].includes(path)) return json([])
      if (['/api/transactions', '/api/goals', '/api/assistant/conversations'].includes(path)) return json(page)
      if (path === '/api/dashboard/summary') return json(summary)
      assert.fail(`Unexpected request ${path}`)
    }
    const { default: App } = await server.ssrLoadModule('/src/App.tsx')
    await Promise.all(['DashboardPage', 'SettingsPage', 'AssistantPage'].map((name) => server.ssrLoadModule(`/src/pages/${name}.tsx`)))
    const { createRoot } = await import('react-dom/client')
    root = createRoot(dom.window.document.getElementById('root'))
    await act(async () => root.render(createElement(StrictMode, null, createElement(App))))
    const sidebar = dom.window.document.querySelector('[data-slot="sidebar-header"]')
    assert.ok(sidebar)
    assert.ok(sidebar.textContent.includes('Abc'))
    assert.ok(sidebar.textContent.includes(backendUser.email))
    assert.match(dom.window.document.body.textContent, /Good to see you, Abc/)
    for (const destination of ['Settings', 'AI Assistant', 'Dashboard']) {
      const button = [...dom.window.document.querySelectorAll('button')].find((item) => item.textContent === destination)
      assert.ok(button, `Missing ${destination} navigation`)
      await act(async () => button.click())
      if (destination === 'Settings') {
        assert.equal(dom.window.document.getElementById('profile-name').value, 'Abc')
        assert.equal(dom.window.document.getElementById('profile-email').value, backendUser.email)
      }
      if (destination === 'AI Assistant') assert.match(dom.window.document.body.textContent, /Hi Abc/)
      assert.doesNotMatch(dom.window.document.body.textContent, /Alex Morgan|alex\.?morgan@example\.com/)
    }
    assert.equal(calls.filter(({ path }) => path === '/api/auth/me').length, 1)
    assert.equal(calls.find(({ path }) => path === '/api/auth/me').url, 'http://localhost:8000/api/auth/me')
    assert.ok(calls.every(({ options }) => options.credentials === 'include'))
  } finally {
    if (root) await act(async () => root.unmount())
    if (client) { client.fetchImpl = originalFetch; client.clearCsrfToken() }
    if (server) await server.close()
    dom.window.close()
    for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] }
  }
})
