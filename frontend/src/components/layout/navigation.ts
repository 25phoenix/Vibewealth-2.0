import {
  Bot,
  ChartNoAxesCombined,
  Goal,
  LayoutDashboard,
  Settings2,
  WalletCards,
  type LucideIcon,
} from 'lucide-react'

export interface NavigationItem {
  label: string
  icon: LucideIcon
  description: string
}

export const navigationItems: NavigationItem[] = [
  { label: 'Dashboard', icon: LayoutDashboard, description: 'Your financial overview' },
  { label: 'Transactions', icon: WalletCards, description: 'Track money coming in and going out' },
  { label: 'Budgets', icon: ChartNoAxesCombined, description: 'Plan spending by category' },
  { label: 'Savings Goals', icon: Goal, description: 'Make progress towards what matters' },
  { label: 'AI Assistant', icon: Bot, description: 'Get context-aware money guidance' },
]

export const settingsItem: NavigationItem = {
  label: 'Settings',
  icon: Settings2,
  description: 'Your preferences and account',
}

