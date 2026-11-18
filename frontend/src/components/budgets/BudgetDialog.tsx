import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FormField } from '@/components/shared/FormField'
import { useAccountCategoryData } from '@/hooks/accountCategoryContext'
import { formatMonth, getIndiaMonthStart } from '@/lib/format'
import { parseAmountToPaise } from '@/lib/money'
import type { BudgetDto, BudgetCreateInput } from '@/types/api'

interface BudgetDialogProps {
  open: boolean
  budget?: BudgetDto
  onOpenChange: (open: boolean) => void
  onSave: (draft: BudgetCreateInput) => Promise<void>
  isSaving?: boolean
}

function rupeesInput(amountPaise: number) {
  const exact = BigInt(amountPaise)
  return `${exact / 100n}.${String(exact % 100n).padStart(2, '0')}`
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
  budget?: BudgetDto
  onCancel: () => void
  onSave: (draft: BudgetCreateInput) => Promise<void>
  isSaving: boolean
}) {
  const { categories, retryCategories } = useAccountCategoryData()
  const [categoryId, setCategoryId] = useState(budget?.category_id ?? '__overall')
  const [limit, setLimit] = useState(budget ? rupeesInput(budget.limit_paise) : '')
  const [error, setError] = useState('')
  const monthStart = budget?.month_start ?? getIndiaMonthStart()
  const expenseCategories = categories.data.filter((item) => item.transaction_type === 'expense')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const limitPaise = parseAmountToPaise(limit)
    if (!limitPaise) return setError('Enter a monthly limit greater than zero with up to two decimal places.')
    try {
      await onSave({ month_start: monthStart, category_id: categoryId === '__overall' ? null : categoryId, limit_paise: limitPaise })
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Could not save budget. Please try again.')
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{budget ? 'Edit budget' : 'Create a budget'}</DialogTitle>
        <DialogDescription>Set a monthly spending limit for all spending or one expense category.</DialogDescription>
      </DialogHeader>
      <form onSubmit={handleSubmit} className="grid gap-4" noValidate>
        <FormField id="budget-category" label="Category">
          <Select value={categoryId} onValueChange={(value) => { if (value) setCategoryId(value) }}>
            <SelectTrigger id="budget-category" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="__overall">Overall monthly budget</SelectItem>{budget?.category_id && !expenseCategories.some((item) => item.id === budget.category_id) && <SelectItem value={budget.category_id}>{budget.category_name ?? 'Archived category'} (archived)</SelectItem>}{expenseCategories.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}</SelectContent>
          </Select>
        </FormField>
        <FormField id="budget-limit" label="Monthly limit (INR)">
          <Input id="budget-limit" type="number" min="0.01" step="0.01" inputMode="decimal" value={limit} onChange={(event) => setLimit(event.target.value)} placeholder="0.00" />
        </FormField>
        {categories.status === 'error' && <div className="grid gap-2"><p role="alert" className="text-sm text-destructive">Could not load categories. Retry before creating or reassigning a category budget.</p><Button type="button" size="sm" variant="outline" onClick={() => void retryCategories()}>Retry categories</Button></div>}
        <p className="text-xs text-muted-foreground">For {formatMonth(monthStart.slice(0, 7))}</p>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSaving}>Cancel</Button>
          <Button type="submit" disabled={isSaving || (categoryId !== '__overall' && categories.status !== 'success')}>{isSaving ? 'Saving…' : budget ? 'Save budget' : 'Create budget'}</Button>
        </DialogFooter>
      </form>
    </>
  )
}
