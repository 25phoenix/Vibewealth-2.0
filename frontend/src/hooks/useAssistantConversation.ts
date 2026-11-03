import { useCallback, useRef, useState } from 'react'
import { useFinance } from './useFinance'
import type { ChatMessage } from '@/types/assistant'

export function useAssistantConversation() {
  const { requestAssistantReply } = useFinance()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isTyping, setIsTyping] = useState(false)
  const generation = useRef(0)

  const sendMessage = useCallback(async (text: string) => {
    const content = text.trim()
    if (!content || isTyping) return
    const createdAt = new Date().toISOString()
    const messageId = crypto.randomUUID()
    const requestGeneration = generation.current
    setMessages((current) => [...current, { id: `user-${messageId}`, role: 'user', content, createdAt }])
    setIsTyping(true)
    try {
      const reply = await requestAssistantReply(content)
      if (generation.current !== requestGeneration) return
      setMessages((current) => [...current, {
        id: `assistant-${messageId}`,
        role: 'assistant',
        content: reply,
        createdAt: new Date().toISOString(),
        isMock: true,
      }])
    } catch {
      if (generation.current !== requestGeneration) return
      setMessages((current) => [...current, {
        id: `assistant-${messageId}`,
        role: 'assistant',
        content: 'I could not prepare a response right now. Please try again.',
        createdAt: new Date().toISOString(),
      }])
    } finally {
      if (generation.current === requestGeneration) setIsTyping(false)
    }
  }, [isTyping, requestAssistantReply])

  const clearConversation = useCallback(() => {
    generation.current += 1
    setMessages([])
    setIsTyping(false)
  }, [])

  return { messages, isTyping, sendMessage, clearConversation }
}
