export function Notice({ message }: { message: string }) {
  if (!message) return null
  return <p role="status" aria-live="polite" className="mb-4 rounded-lg border border-primary/15 bg-secondary px-3 py-2 text-sm text-secondary-foreground">{message}</p>
}
