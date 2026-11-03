import type { ReactNode } from 'react'

interface FormFieldProps {
  id: string
  label: string
  error?: string
  hint?: string
  children: ReactNode
}

export function FormField({ id, label, error, hint, children }: FormFieldProps) {
  const message = error ?? hint
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">{label}</label>
      {children}
      {message && <p className={error ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>{message}</p>}
    </div>
  )
}
