import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FormField } from '@/components/shared/FormField'
import { useFinance } from '@/hooks/useFinance'
import { getCurrentMonthKey } from '@/lib/format'
import { parseAmountToPaise } from '@/lib/money'
import type { Budget, BudgetDraft } from '@/types/finance'

interface BudgetDialogProps {
  open: boolean
  budget?: Budget
  onOpenChange: (open: boolean) => void
  onSave: (draft: BudgetDraft) => Promise<void>
  isSaving?: boolean
}

function rupeesInput(amountPaise: number) {
  return `${Math.floor(amountPaise / 100)}.${String(amountPaise % 100).padStart(2, '0')}`
}

export function BudgetDialog({ open, budget, onOpenChange, onSave, isSaving = false }: BudgetDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        {open && <BudgetForm key={budget?.id ?? 'new'} budget={budget} onCancel={() => onOpenChange(false)} onSave={onSave} isSaving={isSaving} />}
      </DialogContent>
    </Dialog>
  )
}

function BudgetForm({ budget, onCancel, onSave, isSaving }: {
  budget?: Budget
  onCancel: () => void
  onSave: (draft: BudgetDraft) => Promise<void>
  isSaving: boolean
}) {
  const { snapshot } = useFinance()
  const [category, setCategory] = useState(budget?.category ?? '')
  const [limit, setLimit] = useState(budget ? rupeesInput(budget.limitPaise) : '')
  const [error, setError] = useState('')
  const month = budget?.month ?? getCurrentMonthKey()
  const expenseCategories = snapshot.categories.filter((item) => item.type !== 'income')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const limitPaise = parseAmountToPaise(limit)
    if (!category) return setError('Choose a category for this budget.')
    if (!limitPaise) return setError('Enter a monthly limit greater than zero with up to two decimal places.')
    const alreadyExists = snapshot.budgets.some((item) => item.month === month && item.category === category && item.id !== budget?.id)
    if (alreadyExists) return setError('A budget already exists for this category and month.')
    try {
      await onSave({ category, limitPaise, month })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save budget. Please try again.')
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{budget ? 'Edit budget' : 'Create a budget'}</DialogTitle>
        <DialogDescription>Set a monthly spending limit for one category.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="budget-category" label="Category">
          <Select value={category} onValueChange={(value) => { if (value) setCategory(value) }}>
            <SelectTrigger id="budget-category" className="w-full"><SelectValue placeholder="Choose a category" /></SelectTrigger>
            <SelectContent>{expenseCategories.map((item) => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}</SelectContent>
          </Select>
        </FormField>
        <FormField id="budget-limit" label="Monthly limit (INR)">
          <Input id="budget-limit" type="number" min="0.01" step="0.01" inputMode="decimal" value={limit} onChange={(event) => setLimit(event.target.value)} placeholder="0.00" />
        </FormField>
        <p className="text-xs text-muted-foreground">For {new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' }).format(new Date(`${month}-01T00:00:00`))}</p>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving}>{isSaving ? 'Saving…' : budget ? 'Save budget' : 'Create budget'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}
