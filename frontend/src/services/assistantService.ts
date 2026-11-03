export interface AssistantService {
  reply: (question: string) => Promise<string>
}
