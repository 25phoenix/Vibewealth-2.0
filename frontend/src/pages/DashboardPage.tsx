import { lazy, Suspense } from 'react'
import { Banknote, CircleHelp, CreditCard, PiggyBank, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { RecentTransactions } from '@/components/dashboard/RecentTransactions'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import { financeSummary, monthlyChanges } from '@/mocks/dashboard'

const SpendingBreakdown = lazy(() =>
  import('@/components/dashboard/SpendingBreakdown').then((module) => ({ default: module.SpendingBreakdown })),
)

const today = new Intl.DateTimeFormat('en-US', {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
}).format(new Date())

function SpendingBreakdownFallback() {
  return (
    <Card className="dashboard-card gap-0 py-0">
      <CardHeader className="flex-row items-center justify-between space-y-0 px-5 pb-0 pt-5">
        <div className="grid gap-1">
          <p className="section-kicker">SPENDING</p>
          <CardTitle className="text-base">Spending breakdown</CardTitle>
        </div>
        <Skeleton className="h-5 w-20" />
      </CardHeader>
      <CardContent className="grid min-h-64 place-items-center p-5">
        <Skeleton className="size-40 rounded-full" />
      </CardContent>
    </Card>
  )
}

export function DashboardPage() {
  return (
    <div className="page-content">
      <section className="welcome-row" aria-labelledby="welcome-heading">
        <div>
          <p className="date-line">{today}</p>
          <h1 id="welcome-heading">Good morning, Alex</h1>
          <p className="welcome-subtitle">A clear view of your money, all in one place.</p>
        </div>
        <Badge variant="outline" className="sample-badge" title="All figures are sample data">
          <span aria-hidden="true" className="sample-dot" />
          Sample data
          <CircleHelp size={14} aria-hidden="true" />
        </Badge>
      </section>

      <section aria-labelledby="overview-heading" className="overview-section">
        <div className="overview-heading">
          <div>
            <h2 id="overview-heading">Your overview</h2>
            <p>Here’s where things stand this month.</p>
          </div>
          <Badge variant="secondary" className="month-badge">This month</Badge>
        </div>

        <div className="summary-grid" aria-label="Financial summary">
          <SummaryCard label="Total balance" amount={financeSummary.balance} {...monthlyChanges.balance} changeLabel={monthlyChanges.label} icon={Wallet} />
          <SummaryCard label="Income" amount={financeSummary.income} {...monthlyChanges.income} changeLabel={monthlyChanges.label} icon={Banknote} />
          <SummaryCard label="Expenses" amount={financeSummary.expenses} {...monthlyChanges.expenses} changeLabel={monthlyChanges.label} icon={CreditCard} />
          <SummaryCard label="Saved this month" amount={financeSummary.savings} {...monthlyChanges.savings} changeLabel={monthlyChanges.label} icon={PiggyBank} />
        </div>
      </section>

      <section className="dashboard-grid" aria-label="Spending and recent activity">
        <Suspense fallback={<SpendingBreakdownFallback />}>
          <SpendingBreakdown />
        </Suspense>
        <RecentTransactions />
      </section>
    </div>
  )
}
