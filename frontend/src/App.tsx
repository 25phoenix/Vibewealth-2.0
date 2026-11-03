import { lazy, Suspense, useState, type CSSProperties } from 'react'
import { Header } from '@/components/layout/Header'
import { AppSidebar } from '@/components/layout/Sidebar'
import { navigationItems, settingsItem, type NavigationItem } from '@/components/layout/navigation'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { SidebarInset, SidebarProvider, useSidebar } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { FinanceProvider } from '@/hooks/FinanceProvider'
import { useFinance } from '@/hooks/useFinance'
import { useAssistantConversation } from '@/hooks/useAssistantConversation'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import { financeRepository } from '@/services/mockFinanceRepository'
import { mockAssistantService } from '@/services/mockAssistantService'
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
  const assistant = useAssistantConversation()
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
        <Header title={activeItem.label} onAssistantClick={showAssistant} />
        <div id="main-content" className="min-w-0 flex-1" tabIndex={-1}>
          <Suspense fallback={<PageLoadingFallback />}>
            {activeItem.label === 'Dashboard' && <DashboardPage onNavigate={goToPage} />}
            {activeItem.label === 'Transactions' && <TransactionsPage />}
            {activeItem.label === 'Budgets' && <BudgetsPage />}
            {activeItem.label === 'Savings Goals' && <SavingsGoalsPage />}
            {activeItem.label === 'AI Assistant' && <AssistantPage messages={assistant.messages} isTyping={assistant.isTyping} onSend={assistant.sendMessage} onClear={assistant.clearConversation} />}
            {activeItem.label === 'Settings' && <SettingsPage />}
            {!['Dashboard', 'Transactions', 'Budgets', 'Savings Goals', 'AI Assistant', 'Settings'].includes(activeItem.label)
              && <PlaceholderPage item={activeItem} onBack={() => handleNavigate(navigationItems[0])} />}
          </Suspense>
        </div>
      </SidebarInset>
    </>
  )
}

function App() {
  return (
    <FinanceProvider repository={financeRepository} assistantService={mockAssistantService}>
      <TooltipProvider>
        <SidebarProvider
          style={{ '--sidebar-width': '15.5rem', '--sidebar-width-mobile': '18rem' } as CSSProperties}
          className="app-shell"
        >
          <AppFrame />
        </SidebarProvider>
      </TooltipProvider>
    </FinanceProvider>
  )
}

export default App
