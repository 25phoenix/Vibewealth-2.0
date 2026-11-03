import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { transactions } from '@/mocks/dashboard'
import { formatCurrency } from '@/lib/format'

export function RecentTransactions() {
  return (
    <Card className="dashboard-card transactions-panel gap-0 py-0">
      <CardHeader className="panel-header">
        <div className="grid gap-1">
          <p className="section-kicker">RECENT ACTIVITY</p>
          <CardTitle className="text-base">Recent transactions</CardTitle>
        </div>
        <Badge variant="secondary" className="period-badge">Latest</Badge>
      </CardHeader>
      <CardContent className="transactions-content">
        <ul className="transaction-list">
          {transactions.map((transaction) => {
            const isIncome = transaction.type === 'income'
            const DirectionIcon = isIncome ? ArrowDownLeft : ArrowUpRight

            return (
              <li className="transaction-row" key={transaction.id}>
                <span className={`merchant-avatar merchant-${transaction.color}`} aria-hidden="true">{transaction.initials}</span>
                <span className="merchant-copy">
                  <strong>{transaction.merchant}</strong>
                  <span>{transaction.date}</span>
                </span>
                <Badge variant="outline" className="transaction-category">{transaction.category}</Badge>
                <strong className={`transaction-amount ${isIncome ? 'income-amount' : ''}`}>
                  <DirectionIcon aria-hidden="true" size={14} />
                  {isIncome ? '+' : '−'}{formatCurrency(transaction.amount)}
                </strong>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
