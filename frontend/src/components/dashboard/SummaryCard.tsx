import type { LucideIcon } from 'lucide-react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { formatCurrency } from '@/lib/format'

interface SummaryCardProps {
  label: string
  amount: number
  change: string
  changeLabel: string
  direction: 'up' | 'down'
  favorable: boolean
  icon: LucideIcon
}

export function SummaryCard({ label, amount, change, changeLabel, direction, favorable, icon: Icon }: SummaryCardProps) {
  const ChangeIcon = direction === 'up' ? ArrowUpRight : ArrowDownRight
  return (
    <Card className="summary-card gap-0 py-0">
      <CardContent className="grid gap-4 p-4 sm:p-5">
        <div className="summary-topline">
          <span className="summary-label">{label}</span>
          <span className="summary-icon"><Icon size={17} strokeWidth={1.9} /></span>
        </div>
        <div className="summary-amount">{formatCurrency(amount)}</div>
        <div className="summary-change-row">
          <Badge variant="secondary" className={`change-pill ${favorable ? 'change-positive' : 'change-negative'}`}><ChangeIcon size={12} />{change}</Badge>
          <span className="change-caption">{changeLabel}</span>
        </div>
      </CardContent>
    </Card>
  )
}
