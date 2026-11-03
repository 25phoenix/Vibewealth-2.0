import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Bot, LoaderCircle, Send, Sparkles, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmActionDialog } from '@/components/shared/ConfirmActionDialog'
import { PageHeader } from '@/components/shared/PageHeader'
import { useFinance } from '@/hooks/useFinance'
import type { ChatMessage } from '@/types/assistant'

const suggestedPrompts = [
  'Where did my money go this month?',
  'Am I staying within my budgets?',
  'How much can I save this month?',
  'Can I afford a 15,000 rupee purchase?',
  'Which spending categories increased the most?',
]

interface AssistantPageProps {
  messages: ChatMessage[]
  isTyping: boolean
  onSend: (message: string) => void
  onClear: () => void
}

export function AssistantPage({ messages, isTyping, onSend, onClear }: AssistantPageProps) {
  const { snapshot } = useFinance()
  const [draft, setDraft] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, isTyping])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft.trim() || isTyping) return
    onSend(draft)
    setDraft('')
  }

  return (
    <div className="page-content assistant-page">
      <PageHeader
        title="Vibe Assistant"
        description="A thoughtful view of your money, grounded in your sample records."
        action={<Button variant="outline" disabled={messages.length === 0 && !isTyping} onClick={() => setConfirmClear(true)}><Trash2 />Clear chat</Button>}
      />
      <Card className="assistant-card gap-0 py-0">
        <CardHeader className="border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground"><Sparkles size={18} /></span>
            <div className="grid gap-1"><CardTitle className="text-sm">Money conversations, made clearer.</CardTitle><p className="text-xs text-muted-foreground">Ask about your demo budget, spending, or monthly cash flow.</p></div>
          </div>
        </CardHeader>

        <CardContent className="assistant-content">
          {messages.length === 0 ? (
            <div className="assistant-empty">
              <span className="grid size-12 place-items-center rounded-2xl bg-secondary text-primary"><Bot size={22} /></span>
              <div className="grid gap-1 text-center"><h2 className="font-medium text-foreground">Hi {snapshot.profile.name.split(/\s+/)[0]}, what's on your mind?</h2><p className="max-w-md text-sm text-muted-foreground">I can help you explore your sample financial data. These are predefined local responses, not financial advice or a live AI service.</p></div>
              <div className="flex max-w-2xl flex-wrap justify-center gap-2">
                {suggestedPrompts.map((prompt) => <Button key={prompt} variant="outline" size="sm" disabled={isTyping} className="h-auto min-h-9 whitespace-normal text-left" onClick={() => onSend(prompt)}>{prompt}</Button>)}
              </div>
            </div>
          ) : (
            <div className="chat-log" role="log" aria-live="polite" aria-label="Conversation">
              {messages.map((message) => <ChatBubble key={message.id} message={message} />)}
              {isTyping && <div className="chat-assistant"><span className="chat-avatar"><Bot size={16} /></span><div className="chat-bubble"><span className="inline-flex items-center gap-2 text-xs text-muted-foreground"><LoaderCircle size={14} className="animate-spin" />Checking the sample records...</span></div></div>}
              <div ref={bottomRef} />
            </div>
          )}

          <form onSubmit={handleSubmit} className="chat-composer">
            <label htmlFor="assistant-message" className="sr-only">Your message</label>
            <Textarea id="assistant-message" rows={2} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about spending, budgets, or savings..." maxLength={500} disabled={isTyping} />
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] text-muted-foreground">Demo responses use the shared sample dataset.</p>
              <Button type="submit" disabled={!draft.trim() || isTyping} size="sm"><Send />Send</Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <ConfirmActionDialog open={confirmClear} onOpenChange={setConfirmClear} title="Clear this conversation?" description="The messages in this demo session will be removed." confirmLabel="Clear conversation" onConfirm={() => { onClear(); setConfirmClear(false) }} />
    </div>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const time = new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit' }).format(new Date(message.createdAt))
  if (message.role === 'user') {
    return (
      <div className="chat-user">
        <div className="chat-bubble chat-user-bubble"><p>{message.content}</p><time>{time}</time></div>
      </div>
    )
  }

  return (
    <div className="chat-assistant">
      <span className="chat-avatar"><Bot size={16} aria-hidden="true" /></span>
      <div className="chat-bubble">{message.isMock && <span className="chat-mock-label">MOCK RESPONSE</span>}<p>{message.content}</p><time>{time}</time></div>
    </div>
  )
}
