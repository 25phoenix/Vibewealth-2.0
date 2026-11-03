import { Sprout } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from '@/components/ui/sidebar'
import { navigationItems, settingsItem, type NavigationItem } from './navigation'

interface SidebarProps {
  activePage: string
  onNavigate: (item: NavigationItem) => void
}

export function AppSidebar({ activePage, onNavigate }: SidebarProps) {
  const renderItem = (item: NavigationItem) => {
    const Icon = item.icon

    return (
      <SidebarMenuItem key={item.label}>
        <SidebarMenuButton
          isActive={activePage === item.label}
          onClick={() => onNavigate(item)}
          tooltip={item.label}
          className="h-10 rounded-lg px-3 text-[13px] data-active:bg-sidebar-accent data-active:text-sidebar-accent-foreground"
        >
          <Icon aria-hidden="true" />
          <span>{item.label}</span>
        </SidebarMenuButton>
        {item.label === 'AI Assistant' && (
          <SidebarMenuBadge className="right-2 rounded-full bg-primary/10 px-2 text-[10px] font-semibold text-primary">
            New
          </SidebarMenuBadge>
        )}
      </SidebarMenuItem>
    )
  }

  return (
    <Sidebar collapsible="icon" className="border-sidebar-border">
      <SidebarHeader className="gap-5 px-4 pb-4 pt-5">
        <div className="flex items-center gap-2.5 px-1">
          <span className="grid size-8 place-items-center rounded-xl bg-primary text-primary-foreground">
            <Sprout size={18} strokeWidth={2.2} aria-hidden="true" />
          </span>
          <span className="whitespace-nowrap text-[17px] font-semibold tracking-[-0.7px] text-sidebar-foreground">
            vibe<span className="font-normal text-primary">wealth</span>
          </span>
        </div>

        <div className="flex items-center gap-2.5 rounded-xl border border-sidebar-border bg-background/70 p-2.5 group-data-[collapsible=icon]:hidden">
          <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-secondary text-xs font-semibold text-secondary-foreground">A</div>
          <div className="grid min-w-0 gap-0.5">
            <span className="truncate text-xs font-medium text-foreground">Alex Morgan</span>
            <span className="truncate text-[10px] text-muted-foreground">Personal workspace</span>
          </div>
          <Badge variant="outline" className="ml-auto border-transparent bg-secondary px-1.5 text-[9px] text-secondary-foreground">Demo</Badge>
        </div>
      </SidebarHeader>

      <SidebarContent className="px-2">
        <SidebarGroup className="p-0">
          <SidebarGroupLabel className="h-8 px-3 text-[10px] font-semibold tracking-[0.08em] text-muted-foreground">
            YOUR MONEY
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="gap-1">{navigationItems.map(renderItem)}</SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarSeparator className="mx-2 my-3 w-auto" />

        <SidebarGroup className="p-0">
          <SidebarGroupLabel className="h-8 px-3 text-[10px] font-semibold tracking-[0.08em] text-muted-foreground">
            PREFERENCES
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>{renderItem(settingsItem)}</SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-3">
        <div className="flex items-center gap-2.5 rounded-xl border border-sidebar-border p-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:border-transparent">
          <div className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--avatar)] text-[10px] font-semibold text-[var(--avatar-foreground)]">AM</div>
          <div className="grid min-w-0 gap-0.5 group-data-[collapsible=icon]:hidden">
            <span className="truncate text-xs font-medium text-foreground">Alex Morgan</span>
            <span className="truncate text-[10px] text-muted-foreground">Personal plan</span>
          </div>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
