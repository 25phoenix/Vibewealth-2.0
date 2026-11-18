import { useState } from 'react'
import { AlertTriangle, ChartNoAxesCombined, Check, Pencil, Plus, Target, Trash2, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { BudgetDialog } from '@/components/budgets/BudgetDialog'
import { ConfirmActionDialog } from '@/components/shared/ConfirmActionDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { MetricCard } from '@/components/shared/MetricCard'
import { Notice } from '@/components/shared/Notice'
import { PageHeader } from '@/components/shared/PageHeader'
import { useBudgets } from '@/hooks/budgetsContext'
import { formatBasisPoints, formatMonth, formatPaiseExact } from '@/lib/format'
import type { BudgetCreateInput, BudgetDto } from '@/types/api'

function clampProgress(basisPoints: string) {
  const amount = BigInt(basisPoints)
  return Number(amount > 10000n ? 10000n : amount) / 100
}

export function BudgetsPage() {
  const { monthStart, state, mutationError, create, update, remove, isMutating, retry } = useBudgets()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<BudgetDto>()
  const [deleting, setDeleting] = useState<BudgetDto>()
  const month = monthStart.slice(0, 7)
  const budgets = state.data
  const categories = budgets.filter((item) => item.category_id !== null)
  const overall = budgets.find((item) => item.category_id === null)
  const allocated = budgets.reduce((sum, budget) => sum + BigInt(budget.limit_paise), 0n)
  const categorySpent = categories.reduce((sum, budget) => sum + BigInt(budget.actual_spending_paise), 0n)

  const openCreate = () => { setEditing(undefined); setDialogOpen(true) }
  const saveBudget = async (draft: BudgetCreateInput) => {
    if (editing) await update(editing.id, draft)
    else await create(draft)
    setDialogOpen(false); setEditing(undefined)
  }
  const confirmDelete = async () => {
    if (!deleting) return
    try { await remove(deleting.id); setDeleting(undefined) } catch { /* mutationError is shown by the page notice */ }
  }

  return (
    <div className="page-content">
      <PageHeader title="Budgets" description={`Give your spending a plan for ${formatMonth(month)}.`} action={<Button onClick={openCreate} disabled={isMutating}><Plus />Create budget</Button>} />
      <Notice message={mutationError ?? ''} />
      {state.status === 'loading' && <p role="status" className="mb-4">Loading budgets…</p>}
      {state.status === 'error' && <div className="mb-4 grid gap-2"><p role="alert" className="text-sm text-destructive">{state.error}</p><Button variant="outline" onClick={() => void retry()}>Try again</Button></div>}

      <section className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Budget overview">
        <MetricCard label="Total budget allocation" value={formatPaiseExact(allocated)} icon={Wallet} detail={`${budgets.length} monthly budgets`} />
        <MetricCard label="Spending in category budgets" value={formatPaiseExact(categorySpent)} icon={ChartNoAxesCombined} detail="Category budget totals; overall spending is shown separately" />
        <MetricCard label="Overall actual spending" value={overall ? formatPaiseExact(BigInt(overall.actual_spending_paise)) : 'No overall budget'} icon={Target} detail={overall ? `${formatBasisPoints(overall.percent_used_basis_points)}% of overall limit` : 'Create an overall budget to track total spending'} />
      </section>

      {state.status === 'success' && budgets.length === 0 ? (
        <Card><CardContent className="p-0"><EmptyState icon={Wallet} title="Start with a spending plan" description="Create an overall monthly budget or a category budget to see server-calculated spending." action={<Button onClick={openCreate}><Plus />Create a budget</Button>} /></CardContent></Card>
      ) : budgets.length > 0 && (
        <section aria-labelledby="budget-list-heading">
          <div className="mb-3 flex items-center justify-between gap-4"><div><h2 id="budget-list-heading" className="font-semibold text-foreground">Monthly budgets</h2><p className="mt-1 text-xs text-muted-foreground">Spending and remaining amounts are calculated by the backend.</p></div><Badge variant="outline" className="hidden sm:inline-flex">{formatMonth(month)}</Badge></div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {budgets.map((budget) => {
              const remaining = BigInt(budget.remaining_paise)
              const progress = clampProgress(budget.percent_used_basis_points)
              const category = budget.category_name ?? 'Overall monthly budget'
              const status = remaining < 0n ? 'exceeded' : progress >= 80 ? 'approaching' : 'healthy'
              const StatusIcon = status === 'healthy' ? Check : AlertTriangle
              return (
                <Card key={budget.id} className="budget-card gap-0 py-0">
                  <CardHeader className="flex-row items-start justify-between gap-4 px-4 pb-3 pt-4 sm:px-5 sm:pt-5">
                    <div className="grid gap-1"><CardTitle className="text-sm font-semibold">{category}</CardTitle><span className="text-xs text-muted-foreground">Monthly limit {formatPaiseExact(BigInt(budget.limit_paise))}</span></div>
                    <div className="flex items-center gap-1"><Badge variant="secondary" className={`budget-status ${status}`}><StatusIcon size={12} />{status === 'exceeded' ? 'Over limit' : status === 'approaching' ? 'Near limit' : 'On track'}</Badge><Button variant="ghost" size="icon-sm" aria-label={`Edit ${category} budget`} onClick={() => { setEditing(budget); setDialogOpen(true) }}><Pencil /></Button><Button variant="ghost" size="icon-sm" aria-label={`Delete ${category} budget`} onClick={() => setDeleting(budget)}><Trash2 /></Button></div>
                  </CardHeader>
                  <CardContent className="grid gap-3 px-4 pb-4 sm:px-5 sm:pb-5"><Progress aria-label={`${category} budget usage`} value={progress} className={`budget-progress ${status}`} /><div className="flex flex-wrap items-center justify-between gap-2 text-xs"><span className="text-muted-foreground">{formatPaiseExact(BigInt(budget.actual_spending_paise))} spent <span className="text-foreground">({formatBasisPoints(budget.percent_used_basis_points)}%)</span></span><span className={remaining < 0n ? 'font-medium text-negative' : 'text-muted-foreground'}>{formatPaiseExact(remaining < 0n ? -remaining : remaining)} {remaining < 0n ? 'over' : 'left'}</span></div></CardContent>
                </Card>
              )
            })}
          </div>
        </section>
      )}
      <BudgetDialog open={dialogOpen} budget={editing} onOpenChange={setDialogOpen} onSave={saveBudget} isSaving={isMutating} />
      <ConfirmActionDialog open={Boolean(deleting)} pending={isMutating} onOpenChange={(open) => { if (!open && !isMutating) setDeleting(undefined) }} title="Delete this budget?" description="Transactions will remain. Only this spending limit will be removed." onConfirm={confirmDelete} />
    </div>
  )
}
