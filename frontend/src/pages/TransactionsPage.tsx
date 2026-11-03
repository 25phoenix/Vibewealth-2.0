import { useMemo, useState } from 'react'
import { ArrowDownLeft, ArrowDownUp, ArrowUpRight, Pencil, Plus, ReceiptText, Search, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmActionDialog } from '@/components/shared/ConfirmActionDialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { MetricCard } from '@/components/shared/MetricCard'
import { Notice } from '@/components/shared/Notice'
import { PageHeader } from '@/components/shared/PageHeader'
import { TransactionDialog } from '@/components/transactions/TransactionDialog'
import { useFinance } from '@/hooks/useFinance'
import { useNotice } from '@/hooks/useNotice'
import { formatCurrency, formatDate } from '@/lib/format'
import { filterTransactions, summarizeTransactions, type TransactionSort, type TransactionTypeFilter } from '@/services/financeCalculations'
import type { Transaction, TransactionDraft } from '@/types/finance'

export function TransactionsPage() {
  const { snapshot, preferences, addTransaction, updateTransaction, deleteTransaction, isMutating, mutationError } = useFinance()
  const { notice, showNotice } = useNotice()
  const [search, setSearch] = useState('')
  const [type, setType] = useState<TransactionTypeFilter>('all')
  const [category, setCategory] = useState('all')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [sortBy, setSortBy] = useState<TransactionSort>('date-desc')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Transaction>()
  const [deleting, setDeleting] = useState<Transaction>()

  const filtered = useMemo(() => filterTransactions(snapshot.transactions, { search, type, category, from, to, sortBy }), [snapshot.transactions, search, type, category, from, to, sortBy])

  const periodSummary = useMemo(
    () => summarizeTransactions(snapshot.transactions, from || undefined, to || undefined),
    [snapshot.transactions, from, to],
  )

  const openCreate = () => {
    setEditing(undefined)
    setDialogOpen(true)
  }

  const handleSave = async (draft: TransactionDraft) => {
    if (editing) {
      await updateTransaction(editing.id, draft)
      showNotice('Transaction updated. Related summaries have been refreshed.')
    } else {
      await addTransaction(draft)
      showNotice('Transaction added. Your dashboard and budgets are up to date.')
    }
    setDialogOpen(false)
    setEditing(undefined)
  }

  const confirmDelete = async () => {
    if (!deleting) return
    try {
      await deleteTransaction(deleting.id)
      showNotice('Transaction deleted. Related summaries have been refreshed.')
      setDeleting(undefined)
    } catch {
      // The provider exposes the repository error in the page notice.
    }
  }

  return (
    <div className="page-content">
      <PageHeader
        title="Transactions"
        description="Keep track of money coming in and going out. These records are stored in this demo session."
        action={<Button onClick={openCreate} disabled={isMutating}><Plus aria-hidden="true" />Add transaction</Button>}
      />
      <Notice message={mutationError || notice} />

      <section className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3" aria-label="Transaction totals for selected dates">
        <MetricCard label="Income" amountPaise={periodSummary.incomePaise} icon={ArrowDownLeft} detail="For the selected date range" />
        <MetricCard label="Expenses" amountPaise={periodSummary.expensesPaise} icon={ArrowUpRight} detail="For the selected date range" />
        <MetricCard label="Net cash flow" amountPaise={periodSummary.netPaise} icon={ArrowDownUp} detail="Income less expenses" />
      </section>

      <Card className="gap-0 py-0">
        <CardContent className="p-4 sm:p-5">
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <div className="relative sm:col-span-2 xl:col-span-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input aria-label="Search transactions" placeholder="Search transactions" value={search} onChange={(event) => setSearch(event.target.value)} className="pl-9" />
            </div>
            <Select value={type} onValueChange={(value) => { if (value) setType(value as TransactionTypeFilter) }}>
              <SelectTrigger aria-label="Filter by type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                <SelectItem value="income">Income</SelectItem>
                <SelectItem value="expense">Expenses</SelectItem>
              </SelectContent>
            </Select>
            <Select value={category} onValueChange={(value) => { if (value) setCategory(value) }}>
              <SelectTrigger aria-label="Filter by category" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {[...new Set(snapshot.categories.map((item) => item.name))].map((name) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={sortBy} onValueChange={(value) => { if (value) setSortBy(value as TransactionSort) }}>
              <SelectTrigger aria-label="Sort transactions" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="date-desc">Newest first</SelectItem>
                <SelectItem value="date-asc">Oldest first</SelectItem>
                <SelectItem value="amount-desc">Highest amount</SelectItem>
                <SelectItem value="amount-asc">Lowest amount</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="ghost" size="sm" className="justify-self-start text-muted-foreground" onClick={() => { setFrom(''); setTo('') }}>Clear dates</Button>
            <label className="grid gap-1 text-xs text-muted-foreground">From<Input aria-label="From date" type="date" value={from} max={to || undefined} onChange={(event) => setFrom(event.target.value)} /></label>
            <label className="grid gap-1 text-xs text-muted-foreground">To<Input aria-label="To date" type="date" min={from || undefined} onChange={(event) => setTo(event.target.value)} value={to} /></label>
          </div>
          <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>{filtered.length} {filtered.length === 1 ? 'transaction' : 'transactions'}</span>
            {(search || type !== 'all' || category !== 'all' || from || to) && (
              <Button variant="link" size="sm" onClick={() => { setSearch(''); setType('all'); setCategory('all'); setFrom(''); setTo('') }}>Reset filters</Button>
            )}
          </div>

          {filtered.length === 0 ? (
            <EmptyState icon={ReceiptText} title="No transactions match" description="Try changing the search or filters, or add a transaction to get started." action={<Button onClick={openCreate}><Plus />Add transaction</Button>} />
          ) : (
            <div className="transaction-table" role="table" aria-label="Transactions">
              <div className="transaction-table-head" role="row">
                <span role="columnheader">Description</span><span role="columnheader">Category</span><span role="columnheader">Date</span><span role="columnheader">Type</span><span role="columnheader" className="text-right">Amount</span><span role="columnheader" className="sr-only">Actions</span>
              </div>
              <ul className="transaction-list-page" role="rowgroup">
                {filtered.map((transaction) => (
                  <li className="transaction-table-row" key={transaction.id} role="row">
                    <div className="transaction-description" role="cell"><strong>{transaction.description}</strong>{transaction.notes && <small>{transaction.notes}</small>}</div>
                    <span className="table-category" role="cell">{transaction.category}</span>
                    <time dateTime={transaction.date} className="table-date" role="cell">{formatDate(transaction.date)}</time>
                    <span className={`type-label ${transaction.type}`} role="cell">{transaction.type === 'income' ? 'Income' : 'Expense'}</span>
                    <strong className={`table-amount ${transaction.type}`} role="cell">{transaction.type === 'income' ? '+' : '-'}{formatCurrency(transaction.amountPaise, preferences.currency)}</strong>
                    <div className="row-actions" role="cell">
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${transaction.description}`} onClick={() => { setEditing(transaction); setDialogOpen(true) }}><Pencil /></Button>
                      <Button variant="ghost" size="icon-sm" aria-label={`Delete ${transaction.description}`} onClick={() => setDeleting(transaction)}><Trash2 /></Button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <TransactionDialog open={dialogOpen} transaction={editing} onOpenChange={setDialogOpen} onSave={handleSave} isSaving={isMutating} />
      <ConfirmActionDialog open={Boolean(deleting)} pending={isMutating} onOpenChange={(open) => { if (!open && !isMutating) setDeleting(undefined) }} title="Delete this transaction?" description="This cannot be undone. Dashboard and budget totals will update to reflect the deletion." onConfirm={confirmDelete} />
    </div>
  )
}
