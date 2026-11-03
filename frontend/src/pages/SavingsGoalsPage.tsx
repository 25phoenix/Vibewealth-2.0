import { useMemo, useState } from 'react'
import { CalendarDays, Check, Pencil, Plus, Target, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { GoalEditorDialog, GoalMoneyDialog } from '@/components/goals/GoalDialogs'
import { ConfirmActionDialog } from '@/components/shared/ConfirmActionDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { MetricCard } from '@/components/shared/MetricCard'
import { Notice } from '@/components/shared/Notice'
import { PageHeader } from '@/components/shared/PageHeader'
import { useFinance } from '@/hooks/useFinance'
import { useNotice } from '@/hooks/useNotice'
import { formatCurrency, formatDate } from '@/lib/format'
import { getGoalOverview, getGoalProgress } from '@/services/financeCalculations'
import type { SavingsGoal, SavingsGoalDraft } from '@/types/finance'

export function SavingsGoalsPage() {
  const { snapshot, preferences, addGoal, updateGoal, deleteGoal, moveGoalMoney, isMutating, mutationError } = useFinance()
  const { notice, showNotice } = useNotice()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<SavingsGoal>()
  const [deleting, setDeleting] = useState<SavingsGoal>()
  const [movementGoal, setMovementGoal] = useState<SavingsGoal>()
  const [movementDirection, setMovementDirection] = useState<'add' | 'withdraw'>('add')
  const goals = useMemo(() => getGoalProgress(snapshot), [snapshot])
  const overview = getGoalOverview(goals)

  const openCreate = () => { setEditing(undefined); setEditorOpen(true) }
  const saveGoal = async (draft: SavingsGoalDraft) => {
    if (editing) {
      await updateGoal(editing.id, draft)
      showNotice('Savings goal updated.')
    } else {
      await addGoal(draft)
      showNotice('Savings goal created.')
    }
    setEditorOpen(false)
    setEditing(undefined)
  }
  const confirmDelete = async () => {
    if (!deleting) return
    try {
      await deleteGoal(deleting.id)
      showNotice('Savings goal deleted.')
      setDeleting(undefined)
    } catch {
      // The provider exposes the repository error in the page notice.
    }
  }
  const saveMovement = async (amountPaise: number) => {
    if (!movementGoal) return
    await moveGoalMoney(movementGoal.id, amountPaise, movementDirection)
    showNotice(movementDirection === 'add' ? 'Contribution added to your goal.' : 'Money withdrawn from your goal.')
    setMovementGoal(undefined)
  }

  return (
    <div className="page-content">
      <PageHeader title="Savings goals" description="Make steady progress towards the things that matter to you." action={<Button onClick={openCreate} disabled={isMutating}><Plus />New goal</Button>} />
      <Notice message={mutationError || notice} />

      <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="Savings goal overview">
        <MetricCard label="Saved across goals" amountPaise={overview.savedPaise} icon={Target} detail="Goal balances are kept separate from transactions" />
        <MetricCard label="Total target" amountPaise={overview.targetPaise} icon={CalendarDays} detail={`${goals.length} active goals`} />
        <MetricCard label="Still to go" amountPaise={overview.remainingPaise} icon={Check} detail={`${overview.progressPercent}% of total target saved`} />
      </section>

      {goals.length === 0 ? (
        <Card><CardContent className="p-0"><EmptyState icon={Target} title="Give a goal a name" description="Create a savings goal and start tracking progress at your own pace." action={<Button onClick={openCreate}><Plus />Create a goal</Button>} /></CardContent></Card>
      ) : (
        <section aria-labelledby="goal-list-heading">
          <div className="mb-3 flex items-end justify-between gap-4"><div><h2 id="goal-list-heading" className="font-semibold text-foreground">Your goals</h2><p className="mt-1 text-xs text-muted-foreground">Goal contributions are tracked separately from income.</p></div><Badge variant="outline" className="hidden sm:inline-flex">{goals.length} goals</Badge></div>
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {goals.map((goal) => (
              <Card key={goal.id} className="goal-card gap-0 py-0">
                <CardHeader className="flex-row items-start justify-between gap-3 px-4 pb-3 pt-4 sm:px-5 sm:pt-5">
                  <div className="grid gap-1"><CardTitle className="text-sm font-semibold">{goal.name}</CardTitle><span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><CalendarDays size={13} />Target {formatDate(goal.targetDate)}</span></div>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon-sm" aria-label={`Edit ${goal.name}`} onClick={() => { setEditing(goal); setEditorOpen(true) }}><Pencil /></Button>
                    <Button variant="ghost" size="icon-sm" aria-label={`Delete ${goal.name}`} onClick={() => setDeleting(goal)}><Trash2 /></Button>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-4 px-4 pb-4 sm:px-5 sm:pb-5">
                  <div className="flex items-baseline justify-between gap-3">
                    <div><strong className="text-lg font-semibold tabular-nums text-foreground">{formatCurrency(goal.savedPaise, preferences.currency)}</strong><span className="ml-1.5 text-xs text-muted-foreground">saved</span></div>
                    <span className="text-xs text-muted-foreground">of {formatCurrency(goal.targetPaise, preferences.currency)}</span>
                  </div>
                  <Progress aria-label={`${goal.name} progress`} value={goal.progressPercent} className="goal-progress" />
                  <div className="flex items-center justify-between text-xs"><span className="font-medium text-primary">{goal.progressPercent}% complete</span><span className="text-muted-foreground">{formatCurrency(goal.remainingPaise, preferences.currency)} to go</span></div>
                  <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                    <Button size="sm" onClick={() => { setMovementGoal(goal); setMovementDirection('add') }}>Add money</Button>
                    <Button size="sm" variant="outline" disabled={goal.savedPaise === 0} onClick={() => { setMovementGoal(goal); setMovementDirection('withdraw') }}>Withdraw</Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      <GoalEditorDialog open={editorOpen} goal={editing} onOpenChange={setEditorOpen} onSave={saveGoal} isSaving={isMutating} />
      <GoalMoneyDialog open={Boolean(movementGoal)} goal={movementGoal} direction={movementDirection} onOpenChange={(open) => { if (!open) setMovementGoal(undefined) }} onSave={saveMovement} isSaving={isMutating} />
      <ConfirmActionDialog open={Boolean(deleting)} pending={isMutating} onOpenChange={(open) => { if (!open && !isMutating) setDeleting(undefined) }} title="Delete this savings goal?" description="The goal and its tracked balance will be removed. This will not change your transaction history." onConfirm={confirmDelete} />
    </div>
  )
}
