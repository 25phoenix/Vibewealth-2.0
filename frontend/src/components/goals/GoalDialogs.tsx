import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { FormField } from '@/components/shared/FormField'
import { getTodayDateKey, isValidDateKey } from '@/lib/format'
import { parseAmountToPaise } from '@/lib/money'
import type { SavingsGoal, SavingsGoalDraft } from '@/types/finance'

function amountInputValue(amountPaise: number) {
  return `${Math.floor(amountPaise / 100)}.${String(amountPaise % 100).padStart(2, '0')}`
}

interface GoalEditorDialogProps {
  open: boolean
  goal?: SavingsGoal
  onOpenChange: (open: boolean) => void
  onSave: (draft: SavingsGoalDraft) => Promise<void>
  isSaving?: boolean
}

export function GoalEditorDialog({ open, goal, onOpenChange, onSave, isSaving = false }: GoalEditorDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        {open && <GoalEditorForm key={goal?.id ?? 'new'} goal={goal} onCancel={() => onOpenChange(false)} onSave={onSave} isSaving={isSaving} />}
      </DialogContent>
    </Dialog>
  )
}

function GoalEditorForm({ goal, onCancel, onSave, isSaving }: {
  goal?: SavingsGoal
  onCancel: () => void
  onSave: (draft: SavingsGoalDraft) => Promise<void>
  isSaving: boolean
}) {
  const [name, setName] = useState(goal?.name ?? '')
  const [target, setTarget] = useState(goal ? amountInputValue(goal.targetPaise) : '')
  const [targetDate, setTargetDate] = useState(goal?.targetDate ?? '')
  const [error, setError] = useState('')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const targetPaise = parseAmountToPaise(target)
    if (!name.trim()) return setError('Give your goal a name.')
    if (name.trim().length > 60) return setError('Use 60 characters or fewer for the goal name.')
    if (!targetPaise) return setError('Enter a target greater than zero with up to two decimal places.')
    if (!isValidDateKey(targetDate)) return setError('Choose a valid target date.')
    try {
      await onSave({ name: name.trim(), targetPaise, targetDate })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save goal. Please try again.')
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{goal ? 'Edit savings goal' : 'Create a savings goal'}</DialogTitle>
        <DialogDescription>Choose a target and a date to work towards.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="goal-name" label="Goal name">
          <Input id="goal-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={60} autoFocus placeholder="e.g. Emergency fund" />
        </FormField>
        <FormField id="goal-target" label="Target amount (INR)">
          <Input id="goal-target" type="number" min="0.01" step="0.01" inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} placeholder="0.00" />
        </FormField>
        <FormField id="goal-date" label="Target date">
          <Input id="goal-date" type="date" min={getTodayDateKey()} value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
        </FormField>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : goal ? 'Save goal' : 'Create goal'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}

interface GoalMoneyDialogProps {
  open: boolean
  goal?: SavingsGoal
  direction: 'add' | 'withdraw'
  onOpenChange: (open: boolean) => void
  onSave: (amountPaise: number) => Promise<void>
  isSaving?: boolean
}

export function GoalMoneyDialog({ open, goal, direction, onOpenChange, onSave, isSaving = false }: GoalMoneyDialogProps) {
  const key = `${goal?.id ?? 'none'}-${direction}-${open ? 'open' : 'closed'}`
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        {open && goal && <GoalMoneyForm key={key} goal={goal} direction={direction} onCancel={() => onOpenChange(false)} onSave={onSave} isSaving={isSaving} />}
      </DialogContent>
    </Dialog>
  )
}

function GoalMoneyForm({ goal, direction, onCancel, onSave, isSaving }: {
  goal: SavingsGoal
  direction: 'add' | 'withdraw'
  onCancel: () => void
  onSave: (amountPaise: number) => Promise<void>
  isSaving: boolean
}) {
  const [amount, setAmount] = useState('')
  const [error, setError] = useState('')
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const amountPaise = parseAmountToPaise(amount)
    if (!amountPaise) return setError('Enter an amount greater than zero with up to two decimal places.')
    if (direction === 'withdraw' && amountPaise > goal.savedPaise) return setError('You cannot withdraw more than this goal has saved.')
    try {
      await onSave(amountPaise)
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not update goal allocation. Please try again.')
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{direction === 'add' ? 'Add to goal' : 'Withdraw from goal'}</DialogTitle>
        <DialogDescription>{goal.name}. This does not create an income or expense transaction.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="goal-movement" label="Amount (INR)">
          <Input id="goal-movement" type="number" min="0.01" step="0.01" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" autoFocus />
        </FormField>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : direction === 'add' ? 'Add money' : 'Withdraw money'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}
