import { Bell, CircleUserRound, Info, LockKeyhole, Moon, Wallet } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { FormField } from '@/components/shared/FormField'
import { AccountCategorySummary } from '@/components/settings/AccountCategorySummary'
import { PageHeader } from '@/components/shared/PageHeader'
import { useFinance } from '@/hooks/useFinance'
import { useAuth } from '@/hooks/authContext'

export function SettingsPage() {
  const { preferences, updatePreferences } = useFinance()
  const { user } = useAuth()

  return (
    <div className="page-content">
      <PageHeader title="Settings" description="View your account and customise how VibeWealth looks and feels." />

      <div className="grid max-w-4xl gap-4">
        <AccountCategorySummary />

        <Card className="gap-0 py-0">
          <CardHeader className="px-5 pb-1 pt-5">
            <div className="flex items-center gap-2"><CircleUserRound size={17} className="text-primary" /><CardTitle className="text-base">Profile</CardTitle></div>
            <CardDescription>Your authenticated account. Profile editing is not available yet.</CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-4">
            <div className="grid gap-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField id="profile-name" label="Display name">
                  <Input id="profile-name" value={user?.display_name ?? ''} placeholder="Not provided" readOnly />
                </FormField>
                <FormField id="profile-email" label="Email">
                  <Input id="profile-email" type="email" value={user?.email ?? ''} readOnly />
                </FormField>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="gap-0 py-0">
          <CardHeader className="px-5 pb-1 pt-5">
            <div className="flex items-center gap-2"><Wallet size={17} className="text-primary" /><CardTitle className="text-base">Preferences</CardTitle></div>
            <CardDescription>Choose the display options available in this frontend preview.</CardDescription>
          </CardHeader>
          <CardContent className="divide-y divide-border px-5 pb-2 pt-2">
            <div className="flex flex-wrap items-center justify-between gap-4 py-4">
              <div className="grid gap-1"><span className="text-sm font-medium">Currency</span><span className="text-xs text-muted-foreground">The launch currency and displayed account values use INR.</span></div>
              <Badge variant="outline" aria-label="Display currency">INR</Badge>
            </div>
            <div className="flex items-center justify-between gap-4 py-4">
              <div className="flex items-start gap-3"><Moon size={17} className="mt-0.5 text-muted-foreground" /><div className="grid gap-1"><span className="text-sm font-medium">Dark appearance</span><span className="text-xs text-muted-foreground">Apply a darker color theme across the app.</span></div></div>
              <Switch checked={preferences.theme === 'dark'} onCheckedChange={(checked) => updatePreferences({ theme: checked ? 'dark' : 'light' })} aria-label="Dark appearance" />
            </div>
            <div className="flex items-center justify-between gap-4 py-4">
              <div className="flex items-start gap-3"><Bell size={17} className="mt-0.5 text-muted-foreground" /><div className="grid gap-1"><span className="text-sm font-medium">Budget reminders</span><span className="text-xs text-muted-foreground">Save this preference for a future notification service.</span></div></div>
              <Switch checked={preferences.budgetAlerts} onCheckedChange={(checked) => updatePreferences({ budgetAlerts: checked })} aria-label="Budget reminder preference" />
            </div>
            <div className="flex items-center justify-between gap-4 py-4">
              <div className="flex items-start gap-3"><Info size={17} className="mt-0.5 text-muted-foreground" /><div className="grid gap-1"><span className="text-sm font-medium">Weekly money summary</span><span className="text-xs text-muted-foreground">This saves a preference only; no notifications are sent.</span></div></div>
              <Switch checked={preferences.weeklySummary} onCheckedChange={(checked) => updatePreferences({ weeklySummary: checked })} aria-label="Weekly summary preference" />
            </div>
          </CardContent>
        </Card>

        <Card className="gap-0 py-0">
          <CardHeader className="px-5 pb-1 pt-5"><div className="flex items-center gap-2"><LockKeyhole size={17} className="text-primary" /><CardTitle className="text-base">About and privacy</CardTitle></div><CardDescription>VibeWealth 2.0 · frontend preview</CardDescription></CardHeader>
          <CardContent className="px-5 pb-5 pt-3">
            <p className="text-sm leading-relaxed text-muted-foreground">Your identity, accounts, categories, transactions, budgets, savings goals, and dashboard summaries come from your authenticated backend account. Assistant responses still use sample financial data. Display preferences are saved locally in this browser; profile editing is unavailable.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
