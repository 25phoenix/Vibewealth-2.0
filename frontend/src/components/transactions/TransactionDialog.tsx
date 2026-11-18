import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { FormField } from '@/components/shared/FormField'
import { useAccountCategoryData } from '@/hooks/accountCategoryContext'
import { classifyTransactionCreateOutcome } from '@/services/api/transactionOutcome'
import { ResolvedOperationConflictError } from '@/services/api/transactionsApi'
import { createTransactionOperationKey } from '@/services/api/transactionsApi'
import { PendingOperationStorageError } from '@/services/api/pendingTransactionOperation'
import { getTodayDateKey, isValidDateKey } from '@/lib/format'
import { parseAmountToPaise } from '@/lib/money'
import type { TransactionCreateInput, ApiTransactionType } from '@/types/api'

interface TransactionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (input: TransactionCreateInput, idempotencyKey: string) => Promise<void>
  isSaving?: boolean
  recoveryOperationKey?: string | null
}

export function TransactionDialog({ open, onOpenChange, onSave, isSaving = false, recoveryOperationKey = null }: TransactionDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        {open && <TransactionForm onCancel={() => onOpenChange(false)} onSave={onSave} isSaving={isSaving} recoveryOperationKey={recoveryOperationKey} />}
      </DialogContent>
    </Dialog>
  )
}

export function TransactionForm({ onCancel, onSave, isSaving, recoveryOperationKey = null }: {
  onCancel: () => void
  onSave: (input: TransactionCreateInput, idempotencyKey: string) => Promise<void>
  isSaving: boolean
  recoveryOperationKey?: string | null
}) {
  const { accounts, categories } = useAccountCategoryData()
  const today = getTodayDateKey()
  const defaultAccount = accounts.data.find((account) => account.is_default) ?? accounts.data[0]
  const firstExpenseCategory = categories.data.find((item) => item.transaction_type === 'expense')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [type, setType] = useState<ApiTransactionType>('expense')
  const [accountId, setAccountId] = useState(defaultAccount?.id ?? '')
  const [categoryId, setCategoryId] = useState(firstExpenseCategory?.id ?? '')
  const [date, setDate] = useState(today)
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [operation, setOperation] = useState<{ input: TransactionCreateInput; key: string } | null>(null)
  const [outcomeUncertain, setOutcomeUncertain] = useState(false)
  const selectedAccount = accounts.data.find((account) => account.id === accountId)
  const matchingCategories = categories.data.filter((item) => item.transaction_type === type)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (isSaving) return
    if (operation && outcomeUncertain) {
      await submitOperation(operation)
      return
    }
    const amountPaise = parseAmountToPaise(amount)
    const selectedCategory = categories.data.find((item) => item.id === categoryId)
    if (!description.trim()) return setError('Enter a description for this transaction.')
    if (description.trim().length > 120) return setError('Use 120 characters or fewer for the description.')
    if (amountPaise === null) return setError('Enter a positive amount with no more than two decimal places and within the supported limit.')
    if (!selectedAccount) return setError('Choose an account from your backend account list.')
    if (!selectedCategory || selectedCategory.transaction_type !== type) return setError('Choose an active category that matches this transaction type.')
    if (!isValidDateKey(date)) return setError('Choose a valid transaction date.')
    if (date > today) return setError('Transaction date cannot be in the future.')
    if (date < selectedAccount.opening_balance_as_of) return setError('Transaction date cannot be before the account opening date.')

    const nextOperation = {
      input: {
        account_id: selectedAccount.id,
        category_id: selectedCategory.id,
        transaction_type: type,
        amount_paise: amountPaise,
        description: description.trim(),
        transaction_date: date,
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      },
      key: recoveryOperationKey ?? createTransactionOperationKey(),
    }
    setOperation(nextOperation)
    await submitOperation(nextOperation)
  }

  const submitOperation = async (current: { input: TransactionCreateInput; key: string }) => {
    try {
      await onSave(current.input, current.key)
      setOperation(null)
      setOutcomeUncertain(false)
      setError('')
    } catch (saveError) {
      if (saveError instanceof PendingOperationStorageError) {
        setOperation(null)
        setOutcomeUncertain(false)
        setError(saveError instanceof Error ? saveError.message : 'The transaction was rejected.')
        return
      }
      if (saveError instanceof ResolvedOperationConflictError) {
        setOperation(null)
        setOutcomeUncertain(false)
        setError('A previous transaction was saved with different details. It has been recovered. Review the transaction history before submitting again; the next submission will use a new operation.')
        return
      }
      const outcome = classifyTransactionCreateOutcome(saveError)
      const ambiguous = outcome === 'uncertain' || outcome === 'idempotency-conflict' || outcome === 'unauthorized'
      if (ambiguous) {
        setOutcomeUncertain(true)
        setError(saveError instanceof Error && 'status' in saveError && saveError.status === 408
          ? 'The request timed out. It may have been saved; retry the same submission below and do not create it again.'
          : 'We could not confirm whether this transaction was saved. Retry the same submission below; do not create it again.')
      } else {
        setOperation(null)
        setOutcomeUncertain(false)
        setError(saveError instanceof Error ? saveError.message : 'The transaction was rejected.')
      }
    }
  }

  const fieldsDisabled = isSaving || outcomeUncertain

  return (
    <>
      <DialogHeader>
        <DialogTitle>Add transaction</DialogTitle>
        <DialogDescription>Record an income or expense on one of your backend accounts.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="transaction-description" label="Description">
          <Input id="transaction-description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={120} autoFocus disabled={fieldsDisabled} />
        </FormField>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField id="transaction-amount" label="Amount (INR)">
            <Input id="transaction-amount" type="text" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" disabled={fieldsDisabled} />
          </FormField>
          <FormField id="transaction-type" label="Type">
            <Select value={type} onValueChange={(value) => {
              if (value === 'income' || value === 'expense') {
                setType(value)
                setCategoryId(categories.data.find((item) => item.transaction_type === value)?.id ?? '')
                setError('')
              }
            }}>
            <SelectTrigger id="transaction-type" className="w-full" disabled={fieldsDisabled}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="expense">Expense</SelectItem>
                <SelectItem value="income">Income</SelectItem>
              </SelectContent>
            </Select>
          </FormField>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField id="transaction-account" label="Account">
            <Select value={accountId} onValueChange={(value) => { if (value) setAccountId(value) }}>
              <SelectTrigger id="transaction-account" className="w-full" disabled={fieldsDisabled || accounts.status !== 'success'}><SelectValue placeholder="Select an account" /></SelectTrigger>
              <SelectContent>{accounts.data.map((account) => <SelectItem key={account.id} value={account.id}>{account.name}{account.is_default ? ' · Default' : ''}</SelectItem>)}</SelectContent>
            </Select>
          </FormField>
          <FormField id="transaction-category" label="Category">
            <Select value={categoryId} onValueChange={(value) => { if (value) setCategoryId(value) }}>
              <SelectTrigger id="transaction-category" className="w-full" disabled={fieldsDisabled || categories.status !== 'success'}><SelectValue placeholder="Select a category" /></SelectTrigger>
              <SelectContent>{matchingCategories.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
            </Select>
          </FormField>
        </div>
        <FormField id="transaction-date" label="Date">
          <Input id="transaction-date" type="date" min={selectedAccount?.opening_balance_as_of} max={today} value={date} onChange={(event) => setDate(event.target.value)} disabled={fieldsDisabled} />
        </FormField>
        <FormField id="transaction-notes" label="Notes" hint="Optional">
          <Textarea id="transaction-notes" value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} maxLength={4000} disabled={fieldsDisabled} />
        </FormField>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter className="-mx-4 -mb-4">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving || (!outcomeUncertain && (accounts.status !== 'success' || categories.status !== 'success'))}>{isSaving ? 'Saving…' : outcomeUncertain ? 'Retry same transaction' : 'Add transaction'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}
