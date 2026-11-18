import { useEffect, useMemo, useState } from 'react'
import { Plus, ReceiptText, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { EmptyState } from '@/components/shared/EmptyState'
import { Notice } from '@/components/shared/Notice'
import { PageHeader } from '@/components/shared/PageHeader'
import { TransactionDialog } from '@/components/transactions/TransactionDialog'
import { useAccountCategoryData } from '@/hooks/accountCategoryContext'
import { useFinance } from '@/hooks/useFinance'
import { useNotice } from '@/hooks/useNotice'
import { useTransactions } from '@/hooks/transactionsContext'
import { formatCurrency, formatDate } from '@/lib/format'
import type { TransactionCreateInput } from '@/types/api'

const PAGE_SIZE = 50

export function TransactionsPage() {
  const { preferences } = useFinance()
  const { accounts, categories, retryAccounts, retryCategories } = useAccountCategoryData()
  const {
    list,
    query,
    isCreating,
    recovery,
    pendingOperationKey,
    setFilters,
    setOffset,
    resetFilters,
    retryList,
    retryOperationResolution,
    acknowledgeRecovery,
    reconcileInvalidOperation,
    createTransaction,
  } = useTransactions()
  const { notice, showNotice } = useNotice()
  const [search, setSearch] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)

  const visibleTransactions = useMemo(() => {
    const items = list.data?.items ?? []
    const normalizedSearch = search.trim().toLocaleLowerCase()
    if (!normalizedSearch) return items
    return items.filter((transaction) => transaction.description.toLocaleLowerCase().includes(normalizedSearch))
  }, [list.data, search])

  const transactionCount = list.data?.total ?? 0
  const pageItems = list.data?.items ?? []
  const pageStart = pageItems.length === 0 ? 0 : (list.data?.offset ?? 0) + 1
  const pageEnd = (list.data?.offset ?? 0) + pageItems.length
  const hasServerFilters = Boolean(
    query.account_id || query.transaction_type || query.category_id || query.date_from || query.date_to,
  )
  const hasActiveFilters = hasServerFilters || Boolean(search.trim())
  const canCreate = accounts.status === 'success'
    && accounts.data.length > 0
    && categories.status === 'success'
    && categories.data.length > 0
  const canStartTransaction = canCreate
    && ['ready', 'not-found', 'recovered'].includes(recovery.status)

  const handleSave = async (input: TransactionCreateInput, idempotencyKey: string) => {
    await createTransaction(input, idempotencyKey)
    setDialogOpen(false)
    showNotice('Transaction saved to your account. The transaction list and account balance are refreshing.')
  }

  const clearFilters = () => {
    setSearch('')
    resetFilters()
  }

  const openCreateDialog = () => {
    acknowledgeRecovery()
    setDialogOpen(true)
  }

  useEffect(() => {
    if (recovery.status === 'recovered') {
      showNotice('A previously submitted transaction was saved and recovered.')
    }
  }, [recovery.status, showNotice])

  return (
    <div className="page-content">
      <PageHeader
        title="Transactions"
        description="View and add transactions saved to your authenticated account."
        action={<Button onClick={openCreateDialog} disabled={!canStartTransaction || isCreating}><Plus aria-hidden="true" />Add transaction</Button>}
      />
      <Notice message={notice} />

      {recovery.status === 'checking' && <p role="status" aria-live="polite" className="mb-4 text-sm text-muted-foreground">Checking whether a previously submitted transaction was saved…</p>}
      {recovery.status === 'ready' && recovery.message && <p role="status" className="mb-4 text-sm text-muted-foreground">{recovery.message}</p>}
      {recovery.status === 'not-found' && <p role="status" className="mb-4 text-sm text-muted-foreground">{recovery.message} The next submission will reuse its pending operation identity.</p>}
      {recovery.status === 'recovered' && <p role="status" className="mb-4 text-sm text-positive">{recovery.message}</p>}
      {recovery.status === 'error' && <div className="mb-4 flex flex-wrap items-center gap-3"><p role="alert" className="text-sm text-destructive">{recovery.message ?? 'The pending transaction could not be resolved.'}</p><Button variant="outline" size="sm" onClick={() => void retryOperationResolution()}>Retry recovery</Button></div>}
      {recovery.status === 'invalid' && <div className="mb-4 grid gap-2">
        <p role="alert" className="text-sm text-destructive">{recovery.message}</p>
        <p className="text-sm text-muted-foreground">Before proceeding, inspect your transaction history for a possible transaction from the interrupted submission. This cannot prove whether an unidentified operation was saved.</p>
        <Button variant="outline" size="sm" className="justify-self-start" onClick={() => {
          const confirmed = window.confirm('Have you inspected transaction history and do you understand that abandoning this marker means duplicate prevention for the earlier operation cannot be guaranteed?')
          if (confirmed) reconcileInvalidOperation()
        }}>I inspected history; abandon marker</Button>
      </div>}

      {accounts.status === 'error' && <div className="mb-4 flex flex-wrap items-center gap-3"><p role="alert" className="text-sm text-destructive">Account data could not be loaded: {accounts.error}</p><Button variant="outline" size="sm" onClick={() => void retryAccounts()}>Retry accounts</Button></div>}
      {categories.status === 'error' && <div className="mb-4 flex flex-wrap items-center gap-3"><p role="alert" className="text-sm text-destructive">Category data could not be loaded: {categories.error}</p><Button variant="outline" size="sm" onClick={() => void retryCategories()}>Retry categories</Button></div>}
      {accounts.status === 'success' && accounts.data.length === 0 && <p role="status" className="mb-4 text-sm text-muted-foreground">An active account is required before you can add a transaction.</p>}
      {categories.status === 'success' && categories.data.length === 0 && <p role="status" className="mb-4 text-sm text-muted-foreground">An active category is required before you can add a transaction.</p>}

      <Card className="gap-0 py-0">
        <CardContent className="p-4 sm:p-5">
          <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <div className="relative sm:col-span-2 xl:col-span-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input aria-label="Search this page of transactions" placeholder="Search this page" value={search} onChange={(event) => setSearch(event.target.value)} className="pl-9" />
            </div>
            <Select value={query.transaction_type ?? 'all'} onValueChange={(value) => {
              if (value === 'all' || value === 'income' || value === 'expense') {
                setFilters({ transaction_type: value === 'all' ? undefined : value, category_id: undefined })
              }
            }}>
              <SelectTrigger aria-label="Filter by type" className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                <SelectItem value="income">Income</SelectItem>
                <SelectItem value="expense">Expenses</SelectItem>
              </SelectContent>
            </Select>
            <Select value={query.account_id ?? 'all'} onValueChange={(value) => { if (value) setFilters({ account_id: value === 'all' ? undefined : value }) }}>
              <SelectTrigger aria-label="Filter by account" className="w-full" disabled={accounts.status !== 'success'}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All accounts</SelectItem>
                {accounts.data.map((account) => <SelectItem key={account.id} value={account.id}>{account.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={query.category_id ?? 'all'} onValueChange={(value) => { if (value) setFilters({ category_id: value === 'all' ? undefined : value }) }}>
              <SelectTrigger aria-label="Filter by category" className="w-full" disabled={categories.status !== 'success'}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All active categories</SelectItem>
                {categories.data
                  .filter((item) => !query.transaction_type || item.transaction_type === query.transaction_type)
                  .map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="ghost" size="sm" className="justify-self-start text-muted-foreground" onClick={clearFilters}>Reset filters</Button>
            <label className="grid gap-1 text-xs text-muted-foreground">From<Input aria-label="From date" type="date" value={query.date_from ?? ''} max={query.date_to || undefined} onChange={(event) => {
              const dateFrom = event.target.value || undefined
              setFilters({ date_from: dateFrom, ...(dateFrom && query.date_to && dateFrom > query.date_to ? { date_to: undefined } : {}) })
            }} /></label>
            <label className="grid gap-1 text-xs text-muted-foreground">To<Input aria-label="To date" type="date" min={query.date_from || undefined} value={query.date_to ?? ''} onChange={(event) => {
              const dateTo = event.target.value || undefined
              setFilters({ date_to: dateTo, ...(dateTo && query.date_from && dateTo < query.date_from ? { date_from: undefined } : {}) })
            }} /></label>
          </div>

          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{search ? `${visibleTransactions.length} matches on this page` : `Showing ${pageStart}–${pageEnd}`} · {transactionCount} transaction{transactionCount === 1 ? '' : 's'} across server filters</span>
            <span>Newest first · page size {list.data?.limit ?? PAGE_SIZE}</span>
          </div>

          {list.status === 'loading' && <p role="status" aria-live="polite" className="py-10 text-center text-sm text-muted-foreground">Loading transactions…</p>}
          {list.status === 'error' && <div className="grid justify-items-center gap-3 py-10"><p role="alert" className="text-sm text-destructive">Could not load transactions: {list.error}</p><Button variant="outline" onClick={() => void retryList()}>Retry transactions</Button></div>}
          {list.status === 'success' && transactionCount === 0 && hasActiveFilters
            && <EmptyState icon={ReceiptText} title="No transactions match" description={search.trim() ? 'No descriptions on the loaded page match your search. Search covers the loaded page only.' : 'No transaction history matches these server filters. Try changing the filters.'} />}
          {list.status === 'success' && transactionCount === 0 && !hasActiveFilters
            && <EmptyState icon={ReceiptText} title="No transactions yet" description="Add an income or expense to begin your transaction history." action={canStartTransaction ? <Button onClick={openCreateDialog}><Plus />Add transaction</Button> : undefined} />}
          {list.status === 'success' && transactionCount > 0 && visibleTransactions.length === 0 && <EmptyState icon={ReceiptText} title="No transactions match" description={search ? 'No descriptions on this page match your search. Search covers the loaded page only.' : 'Try changing the server filters.'} />}
          {list.status === 'success' && visibleTransactions.length > 0 && (
            <div className="transaction-table" role="table" aria-label="Transactions">
              <div className="transaction-table-head" role="row">
                <span role="columnheader">Description</span><span role="columnheader">Account</span><span role="columnheader">Category</span><span role="columnheader">Date</span><span role="columnheader">Type</span><span role="columnheader" className="text-right">Amount</span>
              </div>
              <ul className="transaction-list-page" role="rowgroup">
                {visibleTransactions.map((transaction) => {
                  const accountName = accounts.data.find((item) => item.id === transaction.account_id)?.name ?? 'Archived or unavailable account'
                  return (
                    <li className="transaction-table-row" key={transaction.id} role="row">
                      <div className="transaction-description" role="cell"><strong>{transaction.description}</strong>{transaction.notes && <small>{transaction.notes}</small>}</div>
                      <span className="table-category" role="cell">{accountName}</span>
                      <span className="table-category" role="cell">{transaction.category_name ?? 'Uncategorized'}</span>
                      <time dateTime={transaction.transaction_date} className="table-date" role="cell">{formatDate(transaction.transaction_date)}</time>
                      <span className={`type-label ${transaction.transaction_type}`} role="cell">{transaction.transaction_type === 'income' ? 'Income' : 'Expense'}</span>
                      <strong className={`table-amount ${transaction.transaction_type}`} role="cell">{transaction.transaction_type === 'income' ? '+' : '-'}{formatCurrency(transaction.amount_paise, preferences.currency)}</strong>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {list.status === 'success' && transactionCount > 0 && <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" size="sm" disabled={(list.data?.offset ?? 0) === 0} onClick={() => setOffset(Math.max(0, (list.data?.offset ?? 0) - (list.data?.limit ?? PAGE_SIZE)))}>Previous</Button>
            <Button variant="outline" size="sm" disabled={(list.data?.offset ?? 0) + pageItems.length >= transactionCount} onClick={() => setOffset((list.data?.offset ?? 0) + (list.data?.limit ?? PAGE_SIZE))}>Next</Button>
          </div>}
        </CardContent>
      </Card>

      <TransactionDialog
        open={dialogOpen && recovery.status !== 'recovered'}
        onOpenChange={setDialogOpen}
        onSave={handleSave}
        isSaving={isCreating}
        recoveryOperationKey={pendingOperationKey}
      />
    </div>
  )
}
