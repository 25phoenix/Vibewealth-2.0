import { ArrowUpRight, Banknote, CalendarDays, CreditCard, PiggyBank, Target, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { RecentTransactions } from '@/components/dashboard/RecentTransactions'
import { MetricCard } from '@/components/shared/MetricCard'
import { PageHeader } from '@/components/shared/PageHeader'
import { useAuth } from '@/hooks/authContext'
import { useDashboard } from '@/hooks/dashboardContext'
import { formatBasisPoints, formatDate, formatMonth, formatPaiseExact, getTodayDateKey } from '@/lib/format'
import type { DashboardSummaryDto } from '@/types/api'

interface DashboardPageProps {
  onNavigate: (page: string) => void
}

function exact(value: string | number): string {
  return formatPaiseExact(BigInt(value))
}

function progressValue(basisPoints: bigint): number {
  const bounded = basisPoints < 0n ? 0n : basisPoints > 10_000n ? 10_000n : basisPoints
  return Number(bounded) / 100
}

function DashboardLoading() {
  return (
    <div className="page-content grid gap-5" aria-label="Loading dashboard summary" role="status" aria-live="polite">
      <div className="summary-grid">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-32" />)}</div>
      <div className="dashboard-grid"><Skeleton className="h-72" /><Skeleton className="h-72" /></div>
      <Skeleton className="h-72" />
    </div>
  )
}

function BudgetOverview({ data, onNavigate }: { data: DashboardSummaryDto; onNavigate: (page: string) => void }) {
  return (
    <Card className="dashboard-card gap-0 py-0">
      <CardHeader className="panel-header">
        <div className="grid gap-1"><p className="section-kicker">MONTHLY PLAN</p><CardTitle className="text-base">Budget overview</CardTitle></div>
        <Button variant="ghost" size="sm" className="h-8 gap-1 px-2 text-xs text-primary" onClick={() => onNavigate('Budgets')}>Budgets <ArrowUpRight size={13} /></Button>
      </CardHeader>
      <CardContent className="grid gap-4 p-5 pt-4">
        {data.budgets.length === 0
          ? <p className="py-8 text-center text-sm text-muted-foreground">No budgets are set for this month.</p>
          : data.budgets.map((budget) => {
            const usedBasisPoints = BigInt(budget.percent_used_basis_points)
            return (
              <div className="grid gap-2" key={budget.id}>
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                  <span className="text-sm font-medium">{budget.category_name ?? 'Overall spending'}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">{formatBasisPoints(budget.percent_used_basis_points)}% used</span>
                </div>
                <Progress value={progressValue(usedBasisPoints)} aria-label={`${budget.category_name ?? 'Overall'} budget utilization`} />
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>{exact(budget.actual_spending_paise)} of {exact(budget.limit_paise)}</span>
                  <span className={BigInt(budget.remaining_paise) < 0n ? 'text-destructive' : ''}>
                    {BigInt(budget.remaining_paise) < 0n ? `${exact(budget.remaining_paise)} over` : `${exact(budget.remaining_paise)} remaining`}
                  </span>
                </div>
              </div>
            )
          })}
      </CardContent>
    </Card>
  )
}

function GoalsOverview({ data, onNavigate }: { data: DashboardSummaryDto; onNavigate: (page: string) => void }) {
  return (
    <Card className="dashboard-card gap-0 py-0">
      <CardHeader className="panel-header">
        <div className="grid gap-1"><p className="section-kicker">SAVING TOWARD</p><CardTitle className="text-base">Savings goals</CardTitle></div>
        <Button variant="ghost" size="sm" className="h-8 gap-1 px-2 text-xs text-primary" onClick={() => onNavigate('Savings Goals')}>All goals <ArrowUpRight size={13} /></Button>
      </CardHeader>
      <CardContent className="grid gap-4 p-5 pt-4">
        {data.goals.length === 0
          ? <p className="py-8 text-center text-sm text-muted-foreground">Create a savings goal to track your progress.</p>
          : data.goals.map((goal) => {
            const target = BigInt(goal.target_paise)
            const allocated = BigInt(goal.allocated_paise)
            const basisPoints = target > 0n ? allocated * 10_000n / target : 0n
            const remaining = BigInt(goal.remaining_target_paise)
            return (
              <div className="grid gap-2" key={goal.id}>
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                  <span className="text-sm font-medium">{goal.name}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {exact(goal.allocated_paise)} of {exact(goal.target_paise)}
                  </span>
                </div>
                <Progress value={progressValue(basisPoints)} aria-label={`${goal.name} savings goal progress`} />
                <div className="flex flex-wrap justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>{formatBasisPoints(basisPoints.toString())}% funded</span>
                  <span className={remaining < 0n ? 'text-positive' : ''}>
                    {remaining < 0n ? `${exact(remaining.toString())} above target` : `${exact(remaining.toString())} to go`}
                  </span>
                </div>
              </div>
            )
          })}
        {data.goals_total > data.goals.length && <p className="text-xs text-muted-foreground">Showing {data.goals.length} of {data.goals_total} goals.</p>}
      </CardContent>
    </Card>
  )
}

export function DashboardPage({ onNavigate }: DashboardPageProps) {
  const auth = useAuth()
  const { summary, retry } = useDashboard()
  const firstName = auth.user?.display_name?.trim().split(/\s+/)[0] || 'there'

  if (summary.status === 'loading') return <DashboardLoading />
  if (summary.status === 'error' || summary.data === null) {
    return (
      <div className="page-content grid gap-5">
        <PageHeader title="Your money, in perspective." description={`Good to see you, ${firstName}.`} />
        <Card><CardContent className="grid justify-items-start gap-3 p-6">
          <p role="alert" className="text-sm text-destructive">{summary.error ?? 'Could not load your financial summary.'}</p>
          <Button onClick={() => void retry()}>Retry summary</Button>
        </CardContent></Card>
      </div>
    )
  }

  const data = summary.data
  const net = BigInt(data.cash_flow.net_paise)
  const month = data.month_start.slice(0, 7)

  return (
    <div className="page-content">
      <section className="welcome-row" aria-labelledby="welcome-heading">
        <div>
          <p className="date-line">{formatDate(getTodayDateKey(), { weekday: 'long', month: 'long', day: 'numeric' })}</p>
          <h1 id="welcome-heading">Your money, in perspective.</h1>
          <p className="welcome-subtitle">Good to see you, {firstName}. Here's your monthly overview.</p>
        </div>
        <Badge variant="outline" className="gap-2"><span aria-hidden="true" className="size-2 rounded-full bg-positive" />Live account data</Badge>
      </section>

      <section aria-labelledby="overview-heading" className="overview-section">
        <div className="overview-heading">
          <div><h2 id="overview-heading">Your overview</h2><p>Financial data through {formatDate(data.financial_date)}.</p></div>
          <Badge variant="secondary" className="month-badge">{formatMonth(month)}</Badge>
        </div>
        <div className="summary-grid" aria-label="Financial summary">
          <MetricCard label="Total balance" value={exact(data.account_totals.balance_paise)} icon={Wallet} detail={`${data.account_totals.account_count} active accounts`} />
          <MetricCard label="Goal allocations" value={exact(data.account_totals.goal_allocated_paise)} icon={Target} detail="Reserved within account balances" />
          <MetricCard label="Available to spend" value={exact(data.account_totals.available_to_spend_paise)} icon={PiggyBank} detail="After goal allocations" />
          <MetricCard label="Income" value={exact(data.cash_flow.income_paise)} icon={Banknote} detail="Recorded this month" />
          <MetricCard label="Expenses" value={exact(data.cash_flow.expenses_paise)} icon={CreditCard} detail="Recorded this month" />
          <MetricCard label="Net cash flow" value={exact(data.cash_flow.net_paise)} icon={CalendarDays} detail="Income less expenses" negative={net < 0n} />
        </div>
      </section>

      <section className="dashboard-grid" aria-label="Budgets and savings goals">
        <BudgetOverview data={data} onNavigate={onNavigate} />
        <GoalsOverview data={data} onNavigate={onNavigate} />
      </section>

      <section className="mt-4" aria-label="Recent account activity">
        <RecentTransactions transactions={data.recent_transactions.items} onViewAll={() => onNavigate('Transactions')} />
      </section>
    </div>
  )
}
