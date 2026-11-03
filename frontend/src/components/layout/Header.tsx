import { ArrowUpRight, Menu, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SidebarTrigger } from '@/components/ui/sidebar'

interface HeaderProps {
  title: string
  onAssistantClick: () => void
}

export function Header({ title, onAssistantClick }: HeaderProps) {
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
      <Button variant="secondary" size="sm" onClick={onAssistantClick} className="ask-vibe rounded-lg px-3 font-medium">
        <Sparkles aria-hidden="true" />
        <span>Ask Vibe</span>
        <ArrowUpRight aria-hidden="true" className="ask-vibe-arrow" />
      </Button>
    </header>
  )
}
