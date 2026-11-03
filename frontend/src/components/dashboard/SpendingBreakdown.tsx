import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { ArrowUpRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency } from '@/lib/format'
import type { CategorySpending } from '@/types/finance'
import type { CurrencyCode } from '@/types/preferences'

interface SpendingBreakdownProps {
  categories: CategorySpending[]
  totalPaise: number
  currency: CurrencyCode
  onViewBudgets: () => void
}

export function SpendingBreakdown({ categories, totalPaise, currency, onViewBudgets }: SpendingBreakdownProps) {
  return (
    <Card className="dashboard-card gap-0 py-0">
      <CardHeader className="panel-header">
        <div className="grid gap-1">
          <p className="section-kicker">SPENDING</p>
          <CardTitle className="text-base">Spending breakdown</CardTitle>
        </div>
          <Button variant="ghost" size="sm" className="h-8 gap-1 px-2 text-xs text-primary" onClick={onViewBudgets}>Budgets <ArrowUpRight size={13} /></Button>
      </CardHeader>
      <CardContent className="spending-content">
        <div className="chart-wrap" role="img" aria-label="Donut chart showing spending by category">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={categories} dataKey="amountPaise" nameKey="category" innerRadius="70%" outerRadius="91%" paddingAngle={3} stroke="none" cornerRadius={4}>
                {categories.map((category, index) => <Cell key={category.category} fill={`var(--chart-${Math.min(index + 1, 5)})`} />)}
              </Pie>
              <Tooltip formatter={(value) => formatCurrency(Number(value), currency)} />
            </PieChart>
          </ResponsiveContainer>
          <div className="chart-center"><span>Total spent</span><strong>{formatCurrency(totalPaise, currency)}</strong></div>
        </div>
        <ul className="category-list">
          {categories.map((category, index) => (
            <li className="category-row" key={category.category}>
              <span className="category-dot" style={{ backgroundColor: `var(--chart-${Math.min(index + 1, 5)})` }} />
              <span className="category-name">{category.category}</span>
              <span className="category-share">{category.sharePercent}%</span>
              <strong className="category-amount">{formatCurrency(category.amountPaise, currency)}</strong>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
