import { useMemo, useState } from 'react'
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
import { useFinance } from '@/hooks/useFinance'
import { useNotice } from '@/hooks/useNotice'
import { formatCurrency, formatMonth, getCurrentMonthKey } from '@/lib/format'
import { getBudgetOverview, getBudgetProgress } from '@/services/financeCalculations'
import type { Budget, BudgetDraft } from '@/types/finance'

export function BudgetsPage() {
  const { snapshot, preferences, addBudget, updateBudget, deleteBudget, isMutating, mutationError } = useFinance()
  const { notice, showNotice } = useNotice()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Budget>()
  const [deleting, setDeleting] = useState<Budget>()
  const month = getCurrentMonthKey()
  const budgets = useMemo(() => getBudgetProgress(snapshot, month), [snapshot, month])
  const overview = getBudgetOverview(snapshot, budgets, month)

  const openCreate = () => { setEditing(undefined); setDialogOpen(true) }
  const saveBudget = async (draft: BudgetDraft) => {
    if (editing) {
      await updateBudget(editing.id, draft)
      showNotice('Budget updated. Category spending has been recalculated.')
    } else {
      await addBudget(draft)
      showNotice('Budget created.')
    }
    setDialogOpen(false)
    setEditing(undefined)
  }
  const confirmDelete = async () => {
    if (!deleting) return
    try {
      await deleteBudget(deleting.id)
      showNotice('Budget deleted.')
      setDeleting(undefined)
    } catch {
      // The provider exposes the repository error in the page notice.
    }
  }

  return (
    <div className="page-content">
      <PageHeader title="Budgets" description={`Give your spending a plan for ${formatMonth(month)}.`} action={<Button onClick={openCreate} disabled={isMutating}><Plus />Create budget</Button>} />
      <Notice message={mutationError || notice} />

      <section className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Budget overview">
        <MetricCard label="Total budget allocation" amountPaise={overview.allocatedPaise} icon={Wallet} detail={`${budgets.length} categories`} />
        <MetricCard label="Spending in budgeted categories" amountPaise={overview.budgetedCategorySpendingPaise} icon={ChartNoAxesCombined} detail={`${overview.utilizationPercent}% of allocation used`} />
        <MetricCard label="Spending in unbudgeted categories" amountPaise={overview.unbudgetedCategorySpendingPaise} icon={Target} detail="Outside category budgets" />
        <MetricCard label="Total actual spending" amountPaise={overview.totalActualSpendingPaise} icon={AlertTriangle} detail="Budgeted plus unbudgeted spending" />
      </section>

      {budgets.length === 0 ? (
        <Card><CardContent className="p-0"><EmptyState icon={Wallet} title="Start with a spending plan" description="Create a monthly category budget to see how your spending is tracking." action={<Button onClick={openCreate}><Plus />Create a budget</Button>} /></CardContent></Card>
      ) : (
        <section aria-labelledby="budget-list-heading">
          <div className="mb-3 flex items-center justify-between gap-4">
            <div><h2 id="budget-list-heading" className="font-semibold text-foreground">Category budgets</h2><p className="mt-1 text-xs text-muted-foreground">Progress updates automatically when completed transactions change. {overview.categoriesToWatch} {overview.categoriesToWatch === 1 ? 'category is' : 'categories are'} near or over its limit.</p></div>
            <Badge variant="outline" className="hidden sm:inline-flex">{formatMonth(month)}</Badge>
          </div>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {budgets.map((budget) => {
              const statusCopy = budget.status === 'exceeded' ? 'Over limit' : budget.status === 'approaching' ? 'Near limit' : 'On track'
              const StatusIcon = budget.status === 'healthy' ? Check : AlertTriangle
              return (
                <Card key={budget.id} className="budget-card gap-0 py-0">
                  <CardHeader className="flex-row items-start justify-between gap-4 px-4 pb-3 pt-4 sm:px-5 sm:pt-5">
                    <div className="grid gap-1"><CardTitle className="text-sm font-semibold">{budget.category}</CardTitle><span className="text-xs text-muted-foreground">Monthly limit {formatCurrency(budget.limitPaise, preferences.currency)}</span></div>
                    <div className="flex items-center gap-1">
                      <Badge variant="secondary" className={`budget-status ${budget.status}`}><StatusIcon size={12} />{statusCopy}</Badge>
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${budget.category} budget`} onClick={() => { setEditing(budget); setDialogOpen(true) }}><Pencil /></Button>
                      <Button variant="ghost" size="icon-sm" aria-label={`Delete ${budget.category} budget`} onClick={() => setDeleting(budget)}><Trash2 /></Button>
                    </div>
                  </CardHeader>
                  <CardContent className="grid gap-3 px-4 pb-4 sm:px-5 sm:pb-5">
                    <Progress aria-label={`${budget.category} budget usage`} value={Math.min(100, budget.usedPercent)} className={`budget-progress ${budget.status}`} />
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="text-muted-foreground">{formatCurrency(budget.spentPaise, preferences.currency)} spent <span className="text-foreground">({budget.usedPercent}%)</span></span>
                      <span className={budget.remainingPaise < 0 ? 'font-medium text-negative' : 'text-muted-foreground'}>{budget.remainingPaise < 0 ? `${formatCurrency(Math.abs(budget.remainingPaise), preferences.currency)} over` : `${formatCurrency(budget.remainingPaise, preferences.currency)} left`}</span>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </section>
      )}

      <BudgetDialog open={dialogOpen} budget={editing} onOpenChange={setDialogOpen} onSave={saveBudget} isSaving={isMutating} />
      <ConfirmActionDialog open={Boolean(deleting)} pending={isMutating} onOpenChange={(open) => { if (!open && !isMutating) setDeleting(undefined) }} title="Delete this budget?" description="Transactions in this category will remain. Only the spending limit will be removed." onConfirm={confirmDelete} />
    </div>
  )
}
