import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FormField } from '@/components/shared/FormField'
import { useAccountCategoryData } from '@/hooks/accountCategoryContext'
import { getTodayDateKey, isValidDateKey } from '@/lib/format'
import { parseAmountToPaise } from '@/lib/money'
import { GoalAllocationOutcomeUnknownError } from '@/services/api/goalsApi'
import type { GoalCreateInput, GoalDto } from '@/types/api'

function amountInputValue(amountPaise: number) {
  const exact = BigInt(amountPaise)
  return `${exact / 100n}.${String(exact % 100n).padStart(2, '0')}`
}

interface GoalEditorDialogProps {
  open: boolean
  goal?: GoalDto
  onOpenChange: (open: boolean) => void
  onSave: (draft: GoalCreateInput) => Promise<void>
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
  goal?: GoalDto
  onCancel: () => void
  onSave: (draft: GoalCreateInput) => Promise<void>
  isSaving: boolean
}) {
  const [name, setName] = useState(goal?.name ?? '')
  const [description, setDescription] = useState(goal?.description ?? '')
  const [target, setTarget] = useState(goal ? amountInputValue(goal.target_paise) : '')
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? '')
  const [error, setError] = useState('')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const targetPaise = parseAmountToPaise(target)
    if (!name.trim()) return setError('Give your goal a name.')
    if (name.trim().length > 100) return setError('Use 100 characters or fewer for the goal name.')
    if (!targetPaise) return setError('Enter a target greater than zero with up to two decimal places.')
    if (targetDate && !isValidDateKey(targetDate)) return setError('Choose a valid target date.')
    if (description.length > 2000) return setError('Use 2,000 characters or fewer for the description.')
    try {
      await onSave({ name: name.trim(), description: description.trim() || null, target_paise: targetPaise, target_date: targetDate || null })
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
        <Input id="goal-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={100} autoFocus placeholder="e.g. Emergency fund" />
        </FormField>
      <FormField id="goal-description" label="Description (optional)"><Textarea id="goal-description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={3} /></FormField>
        <FormField id="goal-target" label="Target amount (INR)">
          <Input id="goal-target" type="number" min="0.01" step="0.01" inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} placeholder="0.00" />
        </FormField>
        <FormField id="goal-date" label="Target date">
          <Input id="goal-date" type="date" min={getTodayDateKey()} value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
        </FormField>
        <p className="-mt-2 text-xs text-muted-foreground">Target date is optional.</p>
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
  goal?: GoalDto
  direction: 'add' | 'withdraw'
  onOpenChange: (open: boolean) => void
  onSave: (accountId: string, amountPaise: number) => Promise<void>
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
  goal: GoalDto
  direction: 'add' | 'withdraw'
  onCancel: () => void
  onSave: (accountId: string, amountPaise: number) => Promise<void>
  isSaving: boolean
}) {
  const [amount, setAmount] = useState('')
  const [outcomeUnknown, setOutcomeUnknown] = useState(false)
  const { accounts, retryAccounts } = useAccountCategoryData()
  const eligibleAccounts = useMemo(() => {
    if (direction === 'add') {
      return accounts.data
        .filter((account) => account.available_to_spend_paise > 0)
        .map((account) => ({ id: account.id, name: account.name, availableToSpendPaise: account.available_to_spend_paise, allocatedPaise: null as number | null }))
    }
    return goal.account_allocations
      .filter((allocation) => allocation.allocated_paise > 0)
      .map((allocation) => ({
        id: allocation.account_id,
        name: accounts.data.find((account) => account.id === allocation.account_id)?.name ?? `Archived account (${allocation.account_id})`,
        availableToSpendPaise: null as number | null,
        allocatedPaise: allocation.allocated_paise,
      }))
  }, [accounts.data, direction, goal.account_allocations])
  const [accountId, setAccountId] = useState(eligibleAccounts[0]?.id ?? '')
  const [error, setError] = useState('')
  const submitting = useRef(false)

  useEffect(() => {
    setAccountId((current) => eligibleAccounts.some((account) => account.id === current)
      ? current
      : eligibleAccounts[0]?.id ?? '')
  }, [eligibleAccounts])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (isSaving || submitting.current || outcomeUnknown) return
    const amountPaise = parseAmountToPaise(amount)
    if (!amountPaise) return setError('Enter an amount greater than zero with up to two decimal places.')
    if (direction === 'add' && accounts.status !== 'success') return setError('Wait for your accounts to finish loading before contributing.')
    const selected = eligibleAccounts.find((account) => account.id === accountId)
    if (!selected) {
      setAccountId(eligibleAccounts[0]?.id ?? '')
      return setError(eligibleAccounts.length === 0
        ? 'No eligible account is available for this allocation.'
        : 'The selected account is no longer eligible. Review the updated selection and submit again.')
    }
    const availableInScope = direction === 'add' ? selected.availableToSpendPaise ?? 0 : selected.allocatedPaise ?? 0
    if (amountPaise > availableInScope) return setError(direction === 'add' ? 'The amount exceeds this account’s available-to-spend balance.' : 'The amount exceeds this goal’s allocation in the selected account.')
    submitting.current = true
    try {
      await onSave(accountId, amountPaise)
    } catch (saveError) {
      if (saveError instanceof GoalAllocationOutcomeUnknownError) setOutcomeUnknown(true)
      setError(saveError instanceof Error ? saveError.message : 'Could not update goal allocation. Please try again.')
    } finally {
      submitting.current = false
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{direction === 'add' ? 'Add to goal' : 'Withdraw from goal'}</DialogTitle>
        <DialogDescription>{goal.name}. This does not create an income or expense transaction.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="goal-account" label="Account">
          <Select value={accountId} onValueChange={(value) => { if (value) setAccountId(value) }} disabled={isSaving || outcomeUnknown || (direction === 'add' && accounts.status !== 'success')}>
            <SelectTrigger id="goal-account" className="w-full"><SelectValue placeholder="Choose an account" /></SelectTrigger>
            <SelectContent>{eligibleAccounts.map((account) => <SelectItem key={account.id} value={account.id}>{account.name}{direction === 'add' ? ` · available ${amountInputValue(account.availableToSpendPaise!)}` : ` · allocated ${amountInputValue(account.allocatedPaise!)}`}</SelectItem>)}</SelectContent>
          </Select>
        </FormField>
        {accounts.status === 'loading' && direction === 'add' && <p role="status" className="text-sm text-muted-foreground">Loading accounts…</p>}
        {accounts.status === 'error' && direction === 'add' && <div className="grid gap-2"><p role="alert" className="text-sm text-destructive">Could not load accounts. {accounts.error || 'Please try again.'}</p><Button type="button" variant="outline" onClick={() => void retryAccounts()} disabled={isSaving}>Retry accounts</Button></div>}
        {accounts.status === 'error' && direction === 'withdraw' && <p role="status" className="text-xs text-muted-foreground">Account names could not be loaded. Withdrawals use this goal’s allocated account IDs.</p>}
        {eligibleAccounts.length === 0 && (direction === 'withdraw' || accounts.status === 'success') && <p role="alert" className="text-sm text-destructive">{direction === 'add' ? 'No account has available funds to allocate.' : 'This goal has no allocation to withdraw from.'}</p>}
        <FormField id="goal-movement" label="Amount (INR)">
          <Input id="goal-movement" type="number" min="0.01" step="0.01" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" autoFocus disabled={isSaving || outcomeUnknown} />
        </FormField>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving || outcomeUnknown || (direction === 'add' && accounts.status !== 'success') || eligibleAccounts.length === 0}>{isSaving ? 'Saving…' : direction === 'add' ? 'Add money' : 'Withdraw money'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}
