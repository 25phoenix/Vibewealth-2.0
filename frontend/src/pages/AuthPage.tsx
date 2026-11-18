import { useState, type FormEvent } from 'react'
import { Sprout } from 'lucide-react'
import { FormField } from '@/components/shared/FormField'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/hooks/authContext'

type AuthMode = 'login' | 'register'
const accountTypeOptions = [
  { value: 'bank', label: 'Bank account' },
  { value: 'cash', label: 'Cash' },
  { value: 'wallet', label: 'Wallet' },
] as const
type AccountTypeOption = typeof accountTypeOptions[number]['value']

export function AuthPage() {
  const auth = useAuth()
  const [mode, setMode] = useState<AuthMode>('login')
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const [accountType, setAccountType] = useState<AccountTypeOption>('bank')
  const [formError, setFormError] = useState<string | null>(null)
  const registering = mode === 'register'

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode)
    setFormError(null)
    auth.clearAuthError()
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setFormError(null)
    auth.clearAuthError()
    if (auth.isSubmitting) return

    if (registering) {
      if (password.length < 15) {
        setFormError('Use a password with at least 15 characters.')
        return
      }
      if (password !== passwordConfirmation) {
        setFormError('The passwords do not match.')
        return
      }
      await auth.register({
        email,
        password,
        display_name: displayName,
        account_type: accountType,
      })
      return
    }

    await auth.login(email, password)
  }

  return (
    <main className="grid min-h-screen place-items-center bg-background px-4 py-8 sm:px-6">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2.5 text-foreground">
          <span className="grid size-10 place-items-center rounded-2xl bg-primary text-primary-foreground">
            <Sprout size={21} aria-hidden="true" />
          </span>
          <span className="text-xl font-semibold tracking-tight">
            vibe<span className="font-normal text-primary">wealth</span>
          </span>
        </div>

        <Card className="border-0 shadow-xl shadow-foreground/5 ring-1 ring-foreground/10">
          <CardHeader className="gap-2 pb-2">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-primary">
              Your money, in perspective
            </p>
            <CardTitle className="text-2xl">
              {registering ? 'Create your account' : 'Welcome back'}
            </CardTitle>
            <CardDescription>
              {registering
                ? 'Set up your secure VibeWealth account to get started.'
                : 'Sign in to continue to VibeWealth.'}
            </CardDescription>
          </CardHeader>

          <CardContent className="grid gap-5">
            <div className="grid grid-cols-2 rounded-xl bg-muted p-1" aria-label="Authentication options">
              <button
                type="button"
                onClick={() => changeMode('login')}
                aria-pressed={!registering}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${!registering ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => changeMode('register')}
                aria-pressed={registering}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${registering ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                Create account
              </button>
            </div>

            <form className="grid gap-4" onSubmit={(event) => void submit(event)}>
              {registering && (
                <FormField id="auth-display-name" label="Name">
                  <Input
                    id="auth-display-name"
                    autoComplete="name"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    maxLength={120}
                    required
                    disabled={auth.isSubmitting}
                  />
                </FormField>
              )}

              <FormField id="auth-email" label="Email address">
                <Input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  disabled={auth.isSubmitting}
                />
              </FormField>

              <FormField
                id="auth-password"
                label="Password"
                hint={registering ? 'Use at least 15 characters.' : undefined}
              >
                <Input
                  id="auth-password"
                  type="password"
                  autoComplete={registering ? 'new-password' : 'current-password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  minLength={registering ? 15 : undefined}
                  disabled={auth.isSubmitting}
                />
              </FormField>

              {registering && (
                <>
                  <FormField id="auth-password-confirmation" label="Confirm password">
                    <Input
                      id="auth-password-confirmation"
                      type="password"
                      autoComplete="new-password"
                      value={passwordConfirmation}
                      onChange={(event) => setPasswordConfirmation(event.target.value)}
                      required
                      minLength={15}
                      disabled={auth.isSubmitting}
                    />
                  </FormField>
                  <FormField id="auth-account-type" label="Your primary account">
                    <select
                      id="auth-account-type"
                      value={accountType}
                      onChange={(event) => {
                        const selected = accountTypeOptions.find((option) => option.value === event.target.value)
                        if (selected) setAccountType(selected.value)
                      }}
                      disabled={auth.isSubmitting}
                      className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                    >
                      {accountTypeOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </FormField>
                </>
              )}

              {(formError || auth.authError) && (
                <p role="alert" aria-live="assertive" className="rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                  {formError ?? auth.authError}
                </p>
              )}

              <Button type="submit" size="lg" disabled={auth.isSubmitting} className="mt-1 w-full">
                {auth.isSubmitting
                  ? (registering ? 'Creating account…' : 'Signing in…')
                  : (registering ? 'Create account' : 'Sign in')}
              </Button>
            </form>

            <p className="text-center text-xs leading-relaxed text-muted-foreground">
              Finance pages currently show sample data and are not connected to your account.
            </p>
          </CardContent>
        </Card>
      </div>
    </main>
  )
}
