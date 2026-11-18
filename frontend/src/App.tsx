import { lazy, Suspense, useState, type CSSProperties } from 'react'
import { Header } from '@/components/layout/Header'
import { AppSidebar } from '@/components/layout/Sidebar'
import { navigationItems, settingsItem, type NavigationItem } from '@/components/layout/navigation'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { SidebarInset, SidebarProvider, useSidebar } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AccountCategoryProvider } from '@/hooks/AccountCategoryProvider'
import { FinanceProvider } from '@/hooks/FinanceProvider'
import { TransactionsProvider } from '@/hooks/TransactionsProvider'
import { BudgetsProvider } from '@/hooks/BudgetsProvider'
import { SavingsGoalsProvider } from '@/hooks/SavingsGoalsProvider'
import { DashboardProvider } from '@/hooks/DashboardProvider'
import { AuthProvider } from '@/hooks/AuthProvider'
import { useAuth } from '@/hooks/authContext'
import { useFinance } from '@/hooks/useFinance'
import { useAssistantConversation } from '@/hooks/useAssistantConversation'
import { AuthPage } from '@/pages/AuthPage'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { getMockFinanceSessionServices } from '@/services/mockFinanceSession'
import type { AuthSessionIdentity } from '@/types/auth'
import './App.css'

const DashboardPage = lazy(() => import('@/pages/DashboardPage').then((module) => ({ default: module.DashboardPage })))
const TransactionsPage = lazy(() => import('@/pages/TransactionsPage').then((module) => ({ default: module.TransactionsPage })))
const BudgetsPage = lazy(() => import('@/pages/BudgetsPage').then((module) => ({ default: module.BudgetsPage })))
const SavingsGoalsPage = lazy(() => import('@/pages/SavingsGoalsPage').then((module) => ({ default: module.SavingsGoalsPage })))
const AssistantPage = lazy(() => import('@/pages/AssistantPage').then((module) => ({ default: module.AssistantPage })))
const SettingsPage = lazy(() => import('@/pages/SettingsPage').then((module) => ({ default: module.SettingsPage })))

function PageLoadingFallback() {
  return <div className="page-content grid gap-4" role="status" aria-live="polite" aria-label="Loading page"><Skeleton className="h-8 w-52" /><Skeleton className="h-28 w-full" /><Skeleton className="h-56 w-full" /></div>
}

function AppFrame() {
  const [activeItem, setActiveItem] = useState<NavigationItem>(navigationItems[0])
  const { setOpenMobile } = useSidebar()
  const assistant = useAssistantConversation(activeItem.label === 'AI Assistant')
  const auth = useAuth()
  const { isLoading, loadError, retryLoad } = useFinance()

  if (isLoading) return <div className="page-content" role="status" aria-live="polite">Loading VibeWealth…</div>
  if (loadError) return <div className="page-content grid justify-items-start gap-3"><p role="alert">Could not load your financial data: {loadError}</p><Button onClick={() => void retryLoad()}>Try again</Button></div>

  const handleNavigate = (item: NavigationItem) => {
    setActiveItem(item)
    setOpenMobile(false)
  }

  const goToPage = (page: string) => {
    const item = [...navigationItems, settingsItem].find((candidate) => candidate.label === page)
    if (item) handleNavigate(item)
  }

  const showAssistant = () => goToPage('AI Assistant')

  return (
    <>
      <AppSidebar activePage={activeItem.label} onNavigate={handleNavigate} />
      <SidebarInset className="main-column">
        <Header
          title={activeItem.label}
          onAssistantClick={showAssistant}
          onLogout={() => void auth.logout()}
          isLoggingOut={auth.isLoggingOut}
        />
        <div className="mx-4 mt-3 rounded-xl border border-primary/15 bg-secondary px-3 py-2 text-xs leading-relaxed text-secondary-foreground sm:mx-6">
          <p role="status" aria-live="polite">
            Signed in as {auth.user?.email}. Accounts, active categories, transactions, budgets, savings goals, and dashboard summaries are connected to this account. Assistant conversations are persistent; generation requires an explicitly approved provider.
          </p>
          {auth.authError && <p role="alert" className="mt-1 text-destructive">{auth.authError}</p>}
        </div>
        <div id="main-content" className="min-w-0 flex-1" tabIndex={-1}>
          <Suspense fallback={<PageLoadingFallback />}>
            {activeItem.label === 'Dashboard' && <DashboardPage onNavigate={goToPage} />}
            {activeItem.label === 'Transactions' && <TransactionsPage />}
            {activeItem.label === 'Budgets' && <BudgetsPage />}
            {activeItem.label === 'Savings Goals' && <SavingsGoalsPage />}
            {activeItem.label === 'AI Assistant' && <AssistantPage messages={assistant.messages} isTyping={assistant.isTyping} onSend={assistant.sendMessage} onClear={assistant.clearConversation} controller={assistant} />}
            {activeItem.label === 'Settings' && <SettingsPage />}
            {!['Dashboard', 'Transactions', 'Budgets', 'Savings Goals', 'AI Assistant', 'Settings'].includes(activeItem.label)
              && <PlaceholderPage item={activeItem} onBack={() => handleNavigate(navigationItems[0])} />}
          </Suspense>
        </div>
      </SidebarInset>
    </>
  )
}

export function SessionGate() {
  const auth = useAuth()

  if (auth.status === 'restoring') {
    return <main className="grid min-h-screen place-items-center px-6" role="status" aria-live="polite">Restoring your secure session…</main>
  }

  if (auth.status === 'restore-error') {
    return (
      <main className="grid min-h-screen place-items-center px-4 py-8">
        <div className="grid w-full max-w-md gap-4 rounded-xl bg-card p-6 text-card-foreground ring-1 ring-foreground/10">
          <div>
            <h1 className="text-lg font-semibold">We couldn’t restore your session</h1>
            <p role="alert" className="mt-2 text-sm text-destructive">{auth.authError}</p>
          </div>
          <Button onClick={() => void auth.retrySessionRestore()}>Try again</Button>
        </div>
      </main>
    )
  }

  if (auth.status === 'reconciling') {
    return <main className="grid min-h-screen place-items-center px-6" role="status" aria-live="polite">Verifying the session accepted by the server…</main>
  }

  if (auth.status === 'reconciliation-error') {
    return (
      <main className="grid min-h-screen place-items-center px-4 py-8">
        <div className="grid w-full max-w-md gap-4 rounded-xl bg-card p-6 text-card-foreground ring-1 ring-foreground/10">
          <div>
            <h1 className="text-lg font-semibold">Your request was accepted</h1>
            <p role="alert" className="mt-2 text-sm text-destructive">{auth.authError}</p>
          </div>
          <Button onClick={() => void auth.retrySessionReconciliation()}>Retry session verification</Button>
        </div>
      </main>
    )
  }

  if (auth.status === 'unauthenticated') return <AuthPage />

  if (auth.sessionIdentity === null || auth.user === null) {
    return <main className="grid min-h-screen place-items-center px-6" role="status">Preparing your session…</main>
  }

  return (
    <AuthenticatedFinanceSession key={auth.sessionIdentity.generation} sessionIdentity={auth.sessionIdentity} userId={auth.user.id} />
  )
}

function AuthenticatedFinanceSession({ sessionIdentity, userId }: { sessionIdentity: AuthSessionIdentity; userId: string }) {
  const services = getMockFinanceSessionServices(sessionIdentity)
  const auth = useAuth()

  return (
    <AccountCategoryProvider sessionIdentity={sessionIdentity} onUnauthorized={auth.logout}>
      <TransactionsProvider userId={userId} sessionGeneration={sessionIdentity.generation} onUnauthorized={auth.logout}>
        <FinanceProvider repository={services.repository} assistantService={services.assistantService}>
          <BudgetsProvider sessionGeneration={sessionIdentity.generation} onUnauthorized={auth.logout}>
          <SavingsGoalsProvider sessionGeneration={sessionIdentity.generation} onUnauthorized={auth.logout}>
          <DashboardProvider sessionGeneration={sessionIdentity.generation} onUnauthorized={auth.logout}>
          <TooltipProvider>
            <SidebarProvider
              style={{ '--sidebar-width': '15.5rem', '--sidebar-width-mobile': '18rem' } as CSSProperties}
              className="app-shell"
            >
              <AppFrame />
            </SidebarProvider>
          </TooltipProvider>
          </DashboardProvider>
          </SavingsGoalsProvider>
          </BudgetsProvider>
        </FinanceProvider>
      </TransactionsProvider>
    </AccountCategoryProvider>
  )
}

function App() {
  return (
    <AuthProvider>
      <SessionGate />
    </AuthProvider>
  )
}

export default App
