import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { FormField } from '@/components/shared/FormField'
import { useFinance } from '@/hooks/useFinance'
import { getTodayDateKey, isValidDateKey } from '@/lib/format'
import { parseAmountToPaise } from '@/lib/money'
import type { Transaction, TransactionDraft, TransactionType } from '@/types/finance'

interface TransactionDialogProps {
  open: boolean
  transaction?: Transaction
  onOpenChange: (open: boolean) => void
  onSave: (draft: TransactionDraft) => Promise<void>
  isSaving?: boolean
}

function amountInputValue(amountPaise: number) {
  const rupees = Math.floor(amountPaise / 100)
  const paise = String(amountPaise % 100).padStart(2, '0')
  return `${rupees}.${paise}`
}

export function TransactionDialog({ open, transaction, onOpenChange, onSave, isSaving = false }: TransactionDialogProps) {
  const key = open ? transaction?.id ?? 'new' : 'closed'
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        {open && <TransactionForm key={key} transaction={transaction} onCancel={() => onOpenChange(false)} onSave={onSave} isSaving={isSaving} />}
      </DialogContent>
    </Dialog>
  )
}

function TransactionForm({ transaction, onCancel, onSave, isSaving }: {
  transaction?: Transaction
  onCancel: () => void
  onSave: (draft: TransactionDraft) => Promise<void>
  isSaving: boolean
}) {
  const { snapshot } = useFinance()
  const [description, setDescription] = useState(transaction?.description ?? '')
  const [amount, setAmount] = useState(transaction ? amountInputValue(transaction.amountPaise) : '')
  const [type, setType] = useState<TransactionType>(transaction?.type ?? 'expense')
  const [category, setCategory] = useState(transaction?.category ?? snapshot.categories.find((item) => item.name === 'Food & dining')?.name ?? 'Other')
  const [date, setDate] = useState(transaction?.date ?? getTodayDateKey())
  const [notes, setNotes] = useState(transaction?.notes ?? '')
  const [error, setError] = useState('')
  const categories = snapshot.categories.filter((item) => item.type === type || item.type === 'both')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const amountPaise = parseAmountToPaise(amount)
    if (!description.trim()) return setError('Enter a description for this transaction.')
    if (description.trim().length > 120) return setError('Use 120 characters or fewer for the description.')
    if (!amountPaise) return setError('Enter an amount greater than zero with up to two decimal places.')
    if (!categories.some((item) => item.name === category)) return setError('Choose a category for this transaction type.')
    if (!isValidDateKey(date)) return setError('Choose a valid transaction date.')

    try {
      await onSave({
        description: description.trim(),
        amountPaise,
        type,
        category,
        date,
        notes: notes.trim() || undefined,
      })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save transaction. Please try again.')
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{transaction ? 'Edit transaction' : 'Add transaction'}</DialogTitle>
        <DialogDescription>Record an income or expense. Values stay in this demo session.</DialogDescription>
      </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="transaction-description" label="Description">
          <Input id="transaction-description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={120} autoFocus />
        </FormField>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField id="transaction-amount" label="Amount (INR)">
            <Input id="transaction-amount" type="number" min="0.01" step="0.01" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" />
          </FormField>
          <FormField id="transaction-type" label="Type">
            <Select value={type} onValueChange={(value) => {
              if (value === 'income' || value === 'expense') {
                setType(value)
                const available = snapshot.categories.find((item) => item.type === value)
                if (available) setCategory(available.name)
              }
            }}>
              <SelectTrigger id="transaction-type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="expense">Expense</SelectItem>
                <SelectItem value="income">Income</SelectItem>
              </SelectContent>
            </Select>
          </FormField>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField id="transaction-category" label="Category">
            <Select value={category} onValueChange={(value) => { if (value) setCategory(value) }}>
              <SelectTrigger id="transaction-category" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>{categories.map((item) => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}</SelectContent>
            </Select>
          </FormField>
          <FormField id="transaction-date" label="Date">
            <Input id="transaction-date" type="date" max={getTodayDateKey()} value={date} onChange={(event) => setDate(event.target.value)} />
          </FormField>
        </div>
        <FormField id="transaction-notes" label="Notes" hint="Optional">
          <Textarea id="transaction-notes" value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} maxLength={300} />
        </FormField>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter className="-mx-4 -mb-4">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : transaction ? 'Save changes' : 'Add transaction'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}
