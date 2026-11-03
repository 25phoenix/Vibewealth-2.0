import { lazy, Suspense } from 'react'
import { Banknote, CircleHelp, CreditCard, PiggyBank, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { RecentTransactions } from '@/components/dashboard/RecentTransactions'
import { MetricCard } from '@/components/shared/MetricCard'
import { useFinance } from '@/hooks/useFinance'
import { formatDate, formatMonth, getCurrentMonthKey, getTodayDateKey } from '@/lib/format'
import { getCategorySpending, getMonthlySummary, getRecentTransactions } from '@/services/financeCalculations'

const SpendingBreakdown = lazy(() =>
  import('@/components/dashboard/SpendingBreakdown').then((module) => ({ default: module.SpendingBreakdown })),
)

function SpendingBreakdownFallback() {
  return (
    <Card className="dashboard-card gap-0 py-0">
      <CardHeader className="flex-row items-center justify-between space-y-0 px-5 pb-0 pt-5">
        <div className="grid gap-1"><p className="section-kicker">SPENDING</p><CardTitle className="text-base">Spending breakdown</CardTitle></div>
        <Skeleton className="h-5 w-20" />
      </CardHeader>
      <CardContent className="grid min-h-64 place-items-center p-5"><Skeleton className="size-40 rounded-full" /></CardContent>
    </Card>
  )
}

interface DashboardPageProps {
  onNavigate: (page: string) => void
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const { snapshot, preferences } = useFinance()
  const month = getCurrentMonthKey()
  const summary = getMonthlySummary(snapshot, month)
  const categorySpending = getCategorySpending(snapshot.transactions, month)
  const recentTransactions = getRecentTransactions(snapshot.transactions, month, 4)
  const firstName = snapshot.profile.name.split(/\s+/)[0]

  return (
    <div className="page-content">
      <section className="welcome-row" aria-labelledby="welcome-heading">
        <div>
          <p className="date-line">{formatDate(getTodayDateKey(), { weekday: 'long', month: 'long', day: 'numeric' })}</p>
          <h1 id="welcome-heading">Your money, in perspective.</h1>
          <p className="welcome-subtitle">Good to see you, {firstName}. Here's your monthly overview.</p>
        </div>
        <Badge variant="outline" className="sample-badge" title="All figures are sample data">
          <span aria-hidden="true" className="sample-dot" />Sample data<CircleHelp size={14} aria-hidden="true" />
        </Badge>
      </section>

      <section aria-labelledby="overview-heading" className="overview-section">
        <div className="overview-heading">
          <div><h2 id="overview-heading">Your overview</h2><p>Here's where things stand this month.</p></div>
          <Badge variant="secondary" className="month-badge">{formatMonth(month)}</Badge>
        </div>
        <div className="summary-grid" aria-label="Financial summary">
          <MetricCard label="Total balance" amountPaise={summary.balancePaise} icon={Wallet} detail="Across recorded transactions" />
          <MetricCard label="Income" amountPaise={summary.incomePaise} icon={Banknote} detail="Recorded this month" />
          <MetricCard label="Expenses" amountPaise={summary.expensesPaise} icon={CreditCard} detail="Recorded this month" />
          <MetricCard label="Net cash flow" amountPaise={summary.netPaise} icon={PiggyBank} detail="Income less expenses" />
        </div>
      </section>

      <section className="dashboard-grid" aria-label="Spending and recent activity">
        <Suspense fallback={<SpendingBreakdownFallback />}>
          <SpendingBreakdown categories={categorySpending} totalPaise={summary.expensesPaise} currency={preferences.currency} onViewBudgets={() => onNavigate('Budgets')} />
        </Suspense>
        <RecentTransactions transactions={recentTransactions} currency={preferences.currency} onViewAll={() => onNavigate('Transactions')} />
      </section>
    </div>
  )
}
