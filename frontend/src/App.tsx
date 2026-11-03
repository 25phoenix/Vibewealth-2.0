import { useState, type CSSProperties } from 'react'
import { Header } from '@/components/layout/Header'
import { AppSidebar } from '@/components/layout/Sidebar'
import { navigationItems, type NavigationItem } from '@/components/layout/navigation'
import { SidebarInset, SidebarProvider, useSidebar } from '@/components/ui/sidebar'
import { TooltipProvider } from '@/components/ui/tooltip'
import { DashboardPage } from '@/pages/DashboardPage'
import { PlaceholderPage } from '@/pages/PlaceholderPage'
import './App.css'

function AppFrame() {
  const [activeItem, setActiveItem] = useState<NavigationItem>(navigationItems[0])
  const { setOpenMobile } = useSidebar()

  const handleNavigate = (item: NavigationItem) => {
    setActiveItem(item)
    setOpenMobile(false)
  }

  const showAssistant = () => {
    const assistantItem = navigationItems.find((item) => item.label === 'AI Assistant')
    if (assistantItem) handleNavigate(assistantItem)
  }

  return (
    <>
      <AppSidebar activePage={activeItem.label} onNavigate={handleNavigate} />
      <SidebarInset className="main-column">
        <Header title={activeItem.label} onAssistantClick={showAssistant} />
        <div id="main-content" className="min-w-0 flex-1" tabIndex={-1}>
          {activeItem.label === 'Dashboard'
            ? <DashboardPage />
            : <PlaceholderPage item={activeItem} onBack={() => handleNavigate(navigationItems[0])} />}
        </div>
      </SidebarInset>
    </>
  )
}

function App() {
  return (
    <TooltipProvider>
      <SidebarProvider
        style={{ '--sidebar-width': '15.5rem', '--sidebar-width-mobile': '18rem' } as CSSProperties}
        className="app-shell"
      >
        <AppFrame />
      </SidebarProvider>
    </TooltipProvider>
  )
}

export default App
