import { Tags, Wallet } from 'lucide-react'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAccountCategoryData } from '@/hooks/accountCategoryContext'
import { formatCurrency, formatDate } from '@/lib/format'
import type { AccountDto, CategoryDto } from '@/types/api'

function AccountDetails({ account }: { account: AccountDto }) {
  return (
    <article className="rounded-xl border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium text-foreground">{account.name}</h3>
          <p className="mt-1 text-xs capitalize text-muted-foreground">{account.account_type} account</p>
        </div>
        {account.is_default && <Badge variant="outline">Default</Badge>}
      </div>
      <dl className="mt-4 grid grid-cols-1 gap-x-5 gap-y-3 text-sm sm:grid-cols-2">
        <div><dt className="text-xs text-muted-foreground">Current balance</dt><dd className="mt-1 font-semibold tabular-nums">{formatCurrency(account.balance_paise)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Available to spend</dt><dd className="mt-1 font-semibold tabular-nums">{formatCurrency(account.available_to_spend_paise)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Allocated to savings goals</dt><dd className="mt-1 tabular-nums">{formatCurrency(account.goal_allocated_paise)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Opening balance</dt><dd className="mt-1 tabular-nums">{formatCurrency(account.opening_balance_paise)} <span className="text-xs text-muted-foreground">as of {formatDate(account.opening_balance_as_of)}</span></dd></div>
      </dl>
    </article>
  )
}

function CategoryGroup({ title, categories }: { title: string; categories: CategoryDto[] }) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-medium text-foreground">{title}</h3>
      <ul className="flex flex-wrap gap-2">
        {categories.map((category) => (
          <li key={category.id}><Badge variant="secondary">{category.name}</Badge></li>
        ))}
      </ul>
    </div>
  )
}

export function AccountCategorySummary() {
  const { accounts, categories, retryAccounts, retryCategories } = useAccountCategoryData()
  const incomeCategories = categories.data.filter((category) => category.transaction_type === 'income')
  const expenseCategories = categories.data.filter((category) => category.transaction_type === 'expense')

  return (
    <div className="grid gap-4" aria-label="Backend account and category data">
      <Card className="gap-0 py-0">
        <CardHeader className="px-5 pb-1 pt-5">
          <div className="flex items-center gap-2"><Wallet size={17} className="text-primary" /><CardTitle className="text-base">Accounts</CardTitle></div>
          <CardDescription>Balances and available-to-spend amounts from your authenticated account.</CardDescription>
        </CardHeader>
        <CardContent className="p-5 pt-4">
          {accounts.status === 'loading' && <p role="status" aria-live="polite" className="text-sm text-muted-foreground">Loading accounts…</p>}
          {accounts.status === 'error' && <div className="grid justify-items-start gap-3"><p role="alert" className="text-sm text-destructive">Could not load accounts: {accounts.error}</p><Button variant="outline" onClick={() => void retryAccounts()}>Retry accounts</Button></div>}
          {accounts.status === 'success' && accounts.data.length === 0 && <EmptyState icon={Wallet} title="No accounts found" description="No active accounts are available for this user." />}
          {accounts.status === 'success' && accounts.data.length > 0 && <div className="grid gap-3 md:grid-cols-2">{accounts.data.map((account) => <AccountDetails key={account.id} account={account} />)}</div>}
        </CardContent>
      </Card>

      <Card className="gap-0 py-0">
        <CardHeader className="px-5 pb-1 pt-5">
          <div className="flex items-center gap-2"><Tags size={17} className="text-primary" /><CardTitle className="text-base">Active categories</CardTitle></div>
          <CardDescription>Backend categories available for future transaction integration.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 p-5 pt-4">
          {categories.status === 'loading' && <p role="status" aria-live="polite" className="text-sm text-muted-foreground">Loading categories…</p>}
          {categories.status === 'error' && <div className="grid justify-items-start gap-3"><p role="alert" className="text-sm text-destructive">Could not load categories: {categories.error}</p><Button variant="outline" onClick={() => void retryCategories()}>Retry categories</Button></div>}
          {categories.status === 'success' && categories.data.length === 0 && <EmptyState icon={Tags} title="No active categories" description="There are no active categories available for this user." />}
          {categories.status === 'success' && categories.data.length > 0 && <>
            <CategoryGroup title="Income" categories={incomeCategories} />
            <CategoryGroup title="Expenses" categories={expenseCategories} />
          </>}
        </CardContent>
      </Card>
    </div>
  )
}
