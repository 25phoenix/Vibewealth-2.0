import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="grid justify-items-center gap-3 px-5 py-12 text-center">
      <span className="grid size-12 place-items-center rounded-2xl bg-secondary text-primary"><Icon size={21} aria-hidden="true" /></span>
      <div className="grid gap-1">
        <h3 className="font-medium text-foreground">{title}</h3>
        <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}
