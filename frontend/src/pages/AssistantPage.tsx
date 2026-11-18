import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Bot, LoaderCircle, Send, Sparkles, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmActionDialog } from '@/components/shared/ConfirmActionDialog'
import { PageHeader } from '@/components/shared/PageHeader'
import { useAuth } from '@/hooks/authContext'
import { authenticatedFirstName } from '@/lib/authIdentity'
import type { useAssistantConversation } from '@/hooks/useAssistantConversation'
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
  onSend: (message: string) => void | Promise<boolean>
  controller?: ReturnType<typeof useAssistantConversation>
  onClear: () => void | Promise<boolean>
}

export function AssistantPage({ messages, isTyping, onSend, onClear, controller }: AssistantPageProps) {
  const { user } = useAuth()
  const [draft, setDraft] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmTracking,setConfirmTracking]=useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages, isTyping])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!draft.trim() || isTyping) return
    const sent=onSend(draft)
    if(sent)void sent.then(accepted=>{if(accepted)setDraft('')})
  }

  return (
    <div className="page-content assistant-page">
      <PageHeader
        title="Vibe Assistant"
        description="A thoughtful view of your money, grounded in your recorded financial data."
        action={<Button variant="outline" disabled={isTyping || !controller?.conversation} onClick={() => setConfirmClear(true)}><Trash2 />Delete conversation</Button>}
      />
      {controller && <section className="grid gap-3" aria-label="Saved conversations">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={isTyping} onClick={controller.newConversation}>New conversation</Button>
          <Button variant="outline" disabled={isTyping} onClick={() => void controller.refresh()}>Refresh / recover</Button>
          <label>Conversation <select aria-label="Saved conversation" value={controller.conversation?.id || ''}
            disabled={isTyping} onChange={e => { if(e.target.value)void controller.select(e.target.value) }}>
            <option value="">Select a saved conversation</option>
            {controller.conversations.map(c => <option key={c.id} value={c.id}>{c.title || 'Untitled conversation'}</option>)}
          </select></label>
          {controller.hasMoreConversations && <Button variant="outline" onClick={() => void controller.loadMoreConversations()}>More conversations</Button>}
        </div>
        {controller.error && <p role="alert">{controller.error}</p>}
        {controller.ambiguous && <p role="status">The last submission has an uncertain outcome. Recover it before submitting again.
          <Button variant="outline" disabled={isTyping} onClick={() => void controller.recover()}>Check operation</Button>
          {controller.canResubmit && <Button disabled={isTyping} onClick={() => void controller.resubmit()}>Resend original operation</Button>}
          <Button variant="outline" disabled={isTyping} onClick={() => void controller.reviewHistory()}>Review original history</Button>
          {controller.historyReviewed && <Button variant="outline" disabled={isTyping} onClick={() => setConfirmTracking(true)}>Stop tracking after review</Button>}
          </p>}
        {controller.turn && <div role="status" className="flex flex-wrap items-center gap-2">
          <span>Turn: {controller.turn.status}{controller.turn.lease_expired ? ' (interrupted)' : ''} · attempt {controller.turn.attempt_no} of 3.</span>
          {controller.turn.error && <span>{controller.turn.error.message}</span>}
          {controller.turn.can_retry && <Button disabled={isTyping} onClick={() => void controller.lifecycle('retry')}>Retry turn</Button>}
          {controller.turn.can_abandon && <Button variant="outline" disabled={isTyping} onClick={() => void controller.lifecycle('abandon')}>Abandon turn</Button>}
        </div>}
        {controller.hasMoreMessages && <Button variant="outline" onClick={() => void controller.loadMoreMessages()}>Load more history</Button>}
      </section>}
      <Card className="assistant-card gap-0 py-0">
        <CardHeader className="border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground"><Sparkles size={18} /></span>
            <div className="grid gap-1"><CardTitle className="text-sm">Money conversations, made clearer.</CardTitle><p className="text-xs text-muted-foreground">Read-only financial summaries. Provider generation is disabled until explicitly approved.</p></div>
          </div>
        </CardHeader>

        <CardContent className="assistant-content">
          {messages.length === 0 ? (
            <div className="assistant-empty">
              <span className="grid size-12 place-items-center rounded-2xl bg-secondary text-primary"><Bot size={22} /></span>
              <div className="grid gap-1 text-center"><h2 className="font-medium text-foreground">Hi {authenticatedFirstName(user)}, what's on your mind?</h2><p className="max-w-md text-sm text-muted-foreground">Explore recorded accounts, budgets, spending and goals. Answers cannot create or change financial records.</p></div>
              <div className="flex max-w-2xl flex-wrap justify-center gap-2">
                {suggestedPrompts.map((prompt) => <Button key={prompt} variant="outline" size="sm" disabled={isTyping || controller?.blocked} className="h-auto min-h-9 whitespace-normal text-left" onClick={() => onSend(prompt)}>{prompt}</Button>)}
              </div>
            </div>
          ) : (
            <div className="chat-log" role="log" aria-live="polite" aria-label="Conversation">
              {messages.map((message) => <ChatBubble key={message.id} message={message} />)}
              {isTyping && <div className="chat-assistant"><span className="chat-avatar"><Bot size={16} /></span><div className="chat-bubble"><span className="inline-flex items-center gap-2 text-xs text-muted-foreground"><LoaderCircle size={14} className="animate-spin" />Waiting for the authenticated backend...</span></div></div>}
              <div ref={bottomRef} />
            </div>
          )}

          <form onSubmit={handleSubmit} className="chat-composer">
            <label htmlFor="assistant-message" className="sr-only">Your message</label>
            <Textarea id="assistant-message" rows={2} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask about spending, budgets, or savings..." maxLength={8000} disabled={isTyping || controller?.blocked} />
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] text-muted-foreground">Only backend-grounded answer text is displayed.</p>
              <Button type="submit" disabled={!draft.trim() || isTyping || controller?.blocked} size="sm"><Send />Send</Button>
            </div>
          </form>
        </CardContent>
      </Card>
      <ConfirmActionDialog open={confirmClear} onOpenChange={setConfirmClear} title="Delete this conversation?" description="This permanently removes its saved messages and turns. Financial records are unaffected." confirmLabel="Delete conversation" pending={isTyping} onConfirm={() => {void Promise.resolve(onClear()).then(result=>{if(result!==false)setConfirmClear(false)})}} />
      <ConfirmActionDialog open={confirmTracking} onOpenChange={setConfirmTracking} title="Stop tracking this uncertain operation?"
        description="History review cannot prove that the original request will not commit later. This only removes your recovery pointer; it does not cancel, resend or roll back anything. A new message could duplicate the original."
        confirmLabel="I understand; stop tracking" onConfirm={()=>{controller?.stopTracking();setConfirmTracking(false)}} />
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
