import { ArrowUpRight, LogOut, Menu, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidebarTrigger } from '@/components/ui/sidebar'

interface HeaderProps {
  title: string
  onAssistantClick: () => void
  onLogout: () => void
  isLoggingOut: boolean
}

export function Header({ title, onAssistantClick, onLogout, isLoggingOut }: HeaderProps) {
  return (
    <header className="topbar">
      <div className="flex min-w-0 items-center gap-2">
        <SidebarTrigger className="size-9 rounded-lg text-muted-foreground hover:bg-secondary hover:text-secondary-foreground">
          <Menu aria-hidden="true" />
          <span className="sr-only">Open navigation</span>
        </SidebarTrigger>
        <div className="breadcrumb">
          <span>My money</span>
          <span aria-hidden="true" className="text-border">/</span>
          <strong>{title}</strong>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button variant="secondary" size="sm" onClick={onAssistantClick} className="ask-vibe rounded-lg px-3 font-medium">
          <Sparkles aria-hidden="true" />
          <span>Ask Vibe</span>
          <ArrowUpRight aria-hidden="true" className="ask-vibe-arrow" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onLogout}
          disabled={isLoggingOut}
          aria-label={isLoggingOut ? 'Signing out' : 'Sign out'}
          className="rounded-lg px-2.5 text-muted-foreground"
        >
          <LogOut aria-hidden="true" />
          <span className="hidden sm:inline">{isLoggingOut ? 'Signing out…' : 'Sign out'}</span>
        </Button>
      </div>
    </header>
  )
}
