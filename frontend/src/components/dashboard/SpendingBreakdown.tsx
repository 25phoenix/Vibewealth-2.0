import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { spendingCategories, spendingTotal } from '@/mocks/dashboard'
import { formatCurrency } from '@/lib/format'

export function SpendingBreakdown() {
  return (
    <Card className="dashboard-card gap-0 py-0">
      <CardHeader className="panel-header">
        <div className="grid gap-1">
          <p className="section-kicker">SPENDING</p>
          <CardTitle className="text-base">Spending breakdown</CardTitle>
        </div>
        <Badge variant="outline" className="period-badge">This month</Badge>
      </CardHeader>
      <CardContent className="spending-content">
        <div className="chart-wrap" role="img" aria-label="Donut chart showing spending by category">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={spendingCategories} dataKey="amount" nameKey="name" innerRadius="70%" outerRadius="91%" paddingAngle={3} stroke="none" cornerRadius={4}>
                {spendingCategories.map((category) => <Cell key={category.name} fill={category.color} />)}
              </Pie>
              <Tooltip formatter={(value) => formatCurrency(Number(value))} />
            </PieChart>
          </ResponsiveContainer>
          <div className="chart-center"><span>Total spent</span><strong>{formatCurrency(spendingTotal)}</strong></div>
        </div>
        <ul className="category-list">
          {spendingCategories.map((category) => (
            <li className="category-row" key={category.name}>
              <span className="category-dot" style={{ backgroundColor: category.color }} />
              <span className="category-name">{category.name}</span>
              <span className="category-share">{category.share}%</span>
              <strong className="category-amount">{formatCurrency(category.amount)}</strong>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
