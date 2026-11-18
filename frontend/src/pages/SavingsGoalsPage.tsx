import { useState } from 'react'
import { CalendarDays, Check, ChevronLeft, ChevronRight, Pencil, Plus, Target, Trash2 } from 'lucide-react'
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
import { useSavingsGoals } from '@/hooks/savingsGoalsContext'
import { useAccountCategoryData } from '@/hooks/accountCategoryContext'
import { formatDate, formatPaiseExact } from '@/lib/format'
import type { GoalCreateInput, GoalDto } from '@/types/api'

const PAGE_SIZE = 50
function percent(goal: GoalDto) {
  if (goal.target_paise <= 0) return '0.00'
  const bps = BigInt(goal.allocated_paise) * 10000n / BigInt(goal.target_paise)
  return `${bps / 100n}.${String(bps % 100n).padStart(2, '0')}`
}

export function SavingsGoalsPage() {
  const { accounts } = useAccountCategoryData()
  const { goals: resource, ledger, selectedGoalId, goalOffset, ledgerOffset, mutationError, selectGoal, setGoalOffset, setLedgerOffset, retryGoals, retryLedger, create, update, remove, contribute, withdraw, isMutating } = useSavingsGoals()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editing, setEditing] = useState<GoalDto>()
  const [deleting, setDeleting] = useState<GoalDto>()
  const [movementGoal, setMovementGoal] = useState<GoalDto>()
  const [movementDirection, setMovementDirection] = useState<'add' | 'withdraw'>('add')
  const goals = resource.data?.items ?? []
  const savedTotal = goals.reduce((sum, goal) => sum + BigInt(goal.allocated_paise), 0n)
  const targetTotal = goals.reduce((sum, goal) => sum + BigInt(goal.target_paise), 0n)
  const remainingTotal = goals.reduce((sum, goal) => sum + BigInt(goal.remaining_target_paise), 0n)
  const overviewPercent = targetTotal > 0n ? (savedTotal * 10000n / targetTotal) : 0n
  const overviewPercentLabel = `${overviewPercent / 100n}.${String(overviewPercent % 100n).padStart(2, '0')}`

  const openCreate = () => { setEditing(undefined); setEditorOpen(true) }
  const saveGoal = async (draft: GoalCreateInput) => {
    if (editing) await update(editing.id, draft)
    else await create(draft)
    setEditorOpen(false); setEditing(undefined)
  }
  const confirmDelete = async () => { if (!deleting) return; try { await remove(deleting.id); setDeleting(undefined) } catch { /* mutationError is shown by the page notice */ } }
  const saveMovement = async (accountId: string, amountPaise: number) => {
    if (!movementGoal) return
    if (movementDirection === 'add') await contribute(movementGoal.id, accountId, amountPaise)
    else await withdraw(movementGoal.id, accountId, amountPaise)
    setMovementGoal(undefined)
  }
  const setLedgerGoal = (goalId: string) => selectGoal(selectedGoalId === goalId ? null : goalId)

  return (
    <div className="page-content">
      <PageHeader title="Savings goals" description="Make steady progress towards the things that matter to you." action={<Button onClick={openCreate} disabled={isMutating}><Plus />New goal</Button>} />
      <Notice message={mutationError ?? ''} />
      {resource.status === 'loading' && <p role="status" className="mb-4">Loading savings goals…</p>}
      {resource.status === 'error' && <div className="mb-4 grid gap-2"><p role="alert" className="text-sm text-destructive">{resource.error}</p><Button variant="outline" onClick={() => void retryGoals()}>Try again</Button></div>}
      <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="Savings goal overview">
        <MetricCard label="Allocated on this page" value={formatPaiseExact(savedTotal)} icon={Target} detail="Virtual allocations; account balances are unchanged" />
        <MetricCard label="Page target total" value={formatPaiseExact(targetTotal)} icon={CalendarDays} detail={`${resource.data?.total ?? 0} goals total`} />
        <MetricCard label="Page remaining target" value={formatPaiseExact(remainingTotal)} icon={Check} detail={`${overviewPercentLabel}% of this page’s target allocated`} />
      </section>

      {resource.status === 'success' && resource.data?.total === 0 ? (
        <Card><CardContent className="p-0"><EmptyState icon={Target} title="Give a goal a name" description="Create a savings goal and start tracking progress at your own pace." action={<Button onClick={openCreate}><Plus />Create a goal</Button>} /></CardContent></Card>
      ) : goals.length > 0 && (
        <section aria-labelledby="goal-list-heading">
          <div className="mb-3 flex items-end justify-between gap-4"><div><h2 id="goal-list-heading" className="font-semibold text-foreground">Your goals</h2><p className="mt-1 text-xs text-muted-foreground">Goal contributions and withdrawals are append-only ledger entries.</p></div><Badge variant="outline" className="hidden sm:inline-flex">{resource.data?.total ?? 0} goals</Badge></div>
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
            {goals.map((goal) => {
              const progressText = percent(goal)
              const progressValue = Math.min(100, Number(BigInt(goal.allocated_paise) * 10000n / BigInt(goal.target_paise)) / 100)
              return <Card key={goal.id} className="goal-card gap-0 py-0">
                <CardHeader className="flex-row items-start justify-between gap-3 px-4 pb-3 pt-4 sm:px-5 sm:pt-5"><div className="grid gap-1"><CardTitle className="text-sm font-semibold">{goal.name}</CardTitle><span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><CalendarDays size={13} />Target {goal.target_date ? formatDate(goal.target_date) : 'date not set'}</span>{goal.description && <p className="mt-1 text-xs text-muted-foreground">{goal.description}</p>}</div><div className="flex gap-1"><Button variant="ghost" size="icon-sm" aria-label={`Edit ${goal.name}`} onClick={() => { setEditing(goal); setEditorOpen(true) }}><Pencil /></Button></div></CardHeader>
                <CardContent className="grid gap-4 px-4 pb-4 sm:px-5 sm:pb-5"><div className="flex items-baseline justify-between gap-3"><div><strong className="text-lg font-semibold tabular-nums text-foreground">{formatPaiseExact(BigInt(goal.allocated_paise))}</strong><span className="ml-1.5 text-xs text-muted-foreground">allocated</span></div><span className="text-xs text-muted-foreground">of {formatPaiseExact(BigInt(goal.target_paise))}</span></div><Progress aria-label={`${goal.name} progress`} value={progressValue} className="goal-progress" /><div className="flex items-center justify-between text-xs"><span className="font-medium text-primary">{progressText}% allocated</span><span className="text-muted-foreground">{formatPaiseExact(BigInt(goal.remaining_target_paise))} to go</span></div>
                  <div className="flex flex-wrap gap-2 border-t border-border pt-3"><Button size="sm" disabled={isMutating} onClick={() => { setMovementGoal(goal); setMovementDirection('add') }}>Contribute</Button><Button size="sm" variant="outline" disabled={!goal.account_allocations.some((allocation) => allocation.allocated_paise > 0)} onClick={() => { setMovementGoal(goal); setMovementDirection('withdraw') }}>Withdraw</Button><Button size="sm" variant="ghost" onClick={() => setLedgerGoal(goal.id)}>{selectedGoalId === goal.id ? 'Hide history' : 'History'}</Button><Button type="button" size="sm" variant="outline" className="text-destructive" aria-label={`Delete ${goal.name}`} disabled={isMutating} onClick={() => setDeleting(goal)}><Trash2 aria-hidden="true" />Delete goal</Button></div>
                  {selectedGoalId === goal.id && <div className="border-t border-border pt-3" aria-live="polite"><h3 className="mb-2 text-sm font-medium">Contribution and withdrawal history</h3>{ledger.status === 'loading' && <p role="status" className="text-xs">Loading history…</p>}{ledger.status === 'error' && <div className="grid gap-2"><p role="alert" className="text-xs text-destructive">{ledger.error}</p><Button size="sm" variant="outline" onClick={() => void retryLedger()}>Retry history</Button></div>}{ledger.status === 'success' && ledger.data?.items.length === 0 && <p className="text-xs text-muted-foreground">No ledger entries yet.</p>}{ledger.status === 'success' && ledger.data && ledger.data.items.length > 0 && <><ul className="grid gap-2">{ledger.data.items.map((entry) => <li key={entry.id} className="flex justify-between gap-3 text-xs"><span>{entry.entry_type === 'contribution' ? 'Contribution' : 'Withdrawal'} · {accounts.data.find((account) => account.id === entry.account_id)?.name ?? 'Account'} · {formatDate(entry.effective_date)}</span><span>{entry.entry_type === 'withdrawal' ? '−' : '+'}{formatPaiseExact(BigInt(entry.amount_paise))}</span></li>)}</ul><div className="mt-3 flex items-center justify-between"><Button size="sm" variant="outline" disabled={ledgerOffset === 0} onClick={() => setLedgerOffset(Math.max(0, ledgerOffset - PAGE_SIZE))}><ChevronLeft />Previous</Button><span className="text-xs text-muted-foreground">{ledger.data.offset + 1}–{ledger.data.offset + ledger.data.items.length} of {ledger.data.total}</span><Button size="sm" variant="outline" disabled={ledgerOffset + PAGE_SIZE >= ledger.data.total} onClick={() => setLedgerOffset(ledgerOffset + PAGE_SIZE)}>Next<ChevronRight /></Button></div></>}</div>}
                </CardContent>
              </Card>
            })}
          </div>
          {resource.data && resource.data.total > PAGE_SIZE && <div className="mt-4 flex items-center justify-between"><Button variant="outline" disabled={goalOffset === 0} onClick={() => setGoalOffset(Math.max(0, goalOffset - PAGE_SIZE))}><ChevronLeft />Previous</Button><span className="text-xs text-muted-foreground">{goalOffset + 1}–{goalOffset + goals.length} of {resource.data.total}</span><Button variant="outline" disabled={goalOffset + PAGE_SIZE >= resource.data.total} onClick={() => setGoalOffset(goalOffset + PAGE_SIZE)}>Next<ChevronRight /></Button></div>}
        </section>
      )}

      <GoalEditorDialog open={editorOpen} goal={editing} onOpenChange={setEditorOpen} onSave={saveGoal} isSaving={isMutating} />
      <GoalMoneyDialog open={Boolean(movementGoal)} goal={movementGoal} direction={movementDirection} onOpenChange={(open) => { if (!open) setMovementGoal(undefined) }} onSave={saveMovement} isSaving={isMutating} />
      <ConfirmActionDialog open={Boolean(deleting)} pending={isMutating} onOpenChange={(open) => { if (!open && !isMutating) setDeleting(undefined) }} title={deleting ? `Delete savings goal “${deleting.name}”?` : 'Delete this savings goal?'} description="The goal is deleted and outstanding allocations are released by the server as compensating ledger entries. Account balances are refreshed." onConfirm={confirmDelete} />
    </div>
  )
}
