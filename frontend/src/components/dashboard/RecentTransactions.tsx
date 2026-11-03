import { ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { formatCurrency, formatDate } from '@/lib/format'
import type { Transaction } from '@/types/finance'
import type { CurrencyCode } from '@/types/preferences'

interface RecentTransactionsProps {
  transactions: Transaction[]
  currency: CurrencyCode
  onViewAll: () => void
}

export function RecentTransactions({ transactions, currency, onViewAll }: RecentTransactionsProps) {
  return (
    <Card className="dashboard-card transactions-panel gap-0 py-0">
      <CardHeader className="panel-header">
        <div className="grid gap-1">
          <p className="section-kicker">RECENT ACTIVITY</p>
          <CardTitle className="text-base">Recent transactions</CardTitle>
        </div>
        <Button variant="ghost" size="sm" className="h-8 gap-1 px-2 text-xs text-primary" onClick={onViewAll}>All transactions <ArrowUpRight size={13} /></Button>
      </CardHeader>
      <CardContent className="transactions-content">
        <ul className="transaction-list">
          {transactions.map((transaction) => {
            const isIncome = transaction.type === 'income'
            const DirectionIcon = isIncome ? ArrowDownLeft : ArrowUpRight

            return (
              <li className="transaction-row" key={transaction.id}>
                <span className={`merchant-avatar merchant-${transaction.type}`} aria-hidden="true">{transaction.description.slice(0, 2).toUpperCase()}</span>
                <span className="merchant-copy">
                  <strong>{transaction.description}</strong>
                  <span>{formatDate(transaction.date)}</span>
                </span>
                <Badge variant="outline" className="transaction-category">{transaction.category}</Badge>
                <strong className={`transaction-amount ${isIncome ? 'income-amount' : 'expense-amount'}`}>
                  <DirectionIcon aria-hidden="true" size={14} />
                  {isIncome ? '+' : '−'}{formatCurrency(transaction.amountPaise, currency)}
                </strong>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
