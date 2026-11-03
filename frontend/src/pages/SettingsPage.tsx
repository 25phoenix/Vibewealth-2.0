import { useState, type FormEvent } from 'react'
import { Bell, CircleUserRound, Info, LockKeyhole, Moon, Save, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { FormField } from '@/components/shared/FormField'
import { Notice } from '@/components/shared/Notice'
import { PageHeader } from '@/components/shared/PageHeader'
import { useFinance } from '@/hooks/useFinance'
import { useNotice } from '@/hooks/useNotice'
import type { UserProfile } from '@/types/finance'

export function SettingsPage() {
  const { snapshot, preferences, updatePreferences, updateProfile, isMutating, mutationError } = useFinance()
  const { notice, showNotice } = useNotice()
  const [profile, setProfile] = useState<UserProfile>(snapshot.profile)
  const [profileError, setProfileError] = useState('')

  const saveProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!profile.name.trim()) return setProfileError('Enter a display name.')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profile.email.trim())) return setProfileError('Enter a valid email address.')
    try {
      await updateProfile({ ...profile, name: profile.name.trim(), email: profile.email.trim() })
      setProfileError('')
      showNotice('Profile updated for this demo session.')
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : 'Could not save profile. Please try again.')
    }
  }

  return (
    <div className="page-content">
      <PageHeader title="Settings" description="Manage your profile and how VibeWealth looks and feels." />
      <Notice message={mutationError || notice} />

      <div className="grid max-w-4xl gap-4">
        <Card className="gap-0 py-0">
          <CardHeader className="px-5 pb-1 pt-5">
            <div className="flex items-center gap-2"><CircleUserRound size={17} className="text-primary" /><CardTitle className="text-base">Profile</CardTitle></div>
            <CardDescription>Your demo profile information is kept in this browser session.</CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-4">
            <form onSubmit={saveProfile} className="grid gap-4" noValidate>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormField id="profile-name" label="Display name">
                  <Input id="profile-name" value={profile.name} onChange={(event) => setProfile((current) => ({ ...current, name: event.target.value }))} maxLength={80} />
                </FormField>
                <FormField id="profile-email" label="Email">
                  <Input id="profile-email" type="email" value={profile.email} onChange={(event) => setProfile((current) => ({ ...current, email: event.target.value }))} />
                </FormField>
              </div>
              <FormField id="profile-occupation" label="About you" hint="Optional">
                <Input id="profile-occupation" value={profile.occupation} onChange={(event) => setProfile((current) => ({ ...current, occupation: event.target.value }))} maxLength={100} />
              </FormField>
              {profileError && <p role="alert" className="text-sm text-destructive">{profileError}</p>}
              <div><Button type="submit" disabled={isMutating}>{isMutating ? 'Saving…' : <><Save />Save profile</>}</Button></div>
            </form>
          </CardContent>
        </Card>

        <Card className="gap-0 py-0">
          <CardHeader className="px-5 pb-1 pt-5">
            <div className="flex items-center gap-2"><Wallet size={17} className="text-primary" /><CardTitle className="text-base">Preferences</CardTitle></div>
            <CardDescription>Choose the display options available in this frontend preview.</CardDescription>
          </CardHeader>
          <CardContent className="divide-y divide-border px-5 pb-2 pt-2">
            <div className="flex flex-wrap items-center justify-between gap-4 py-4">
              <div className="grid gap-1"><span className="text-sm font-medium">Currency</span><span className="text-xs text-muted-foreground">Financial records are denominated in INR in this demo.</span></div>
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
            <p className="text-sm leading-relaxed text-muted-foreground">All financial records shown in this build are mock data. Profile and preference changes are local to this frontend; there is no account, backend, or notification service connected.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
