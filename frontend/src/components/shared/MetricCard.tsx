import type { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { formatCurrency } from '@/lib/format'
import { useFinance } from '@/hooks/useFinance'

interface MetricCardProps {
  label: string
  amountPaise?: number
  value?: string
  icon: LucideIcon
  detail?: string
}

export function MetricCard({ label, amountPaise, value, icon: Icon, detail }: MetricCardProps) {
  const { preferences } = useFinance()
  return (
    <Card className="gap-0 py-0">
      <CardContent className="grid gap-3 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-muted-foreground">{label}</span>
          <span className="grid size-8 place-items-center rounded-lg bg-secondary text-primary"><Icon size={16} aria-hidden="true" /></span>
        </div>
        <strong className="tabular-nums text-xl font-semibold tracking-tight text-foreground">{value ?? formatCurrency(amountPaise ?? 0, preferences.currency)}</strong>
        {detail && <span className="text-[11px] text-muted-foreground">{detail}</span>}
      </CardContent>
    </Card>
  )
}
