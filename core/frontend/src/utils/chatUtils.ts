import type { Message, MessageContent, Chat } from '@/components/models/types'

// Generate a human-readable filename with timestamp
export function generateFilename(prefix: string, extension: string): string {
  const now = new Date()
  const date = now.toISOString().split('T')[0] // YYYY-MM-DD
  const time = now.toTimeString().split(' ')[0].replace(/:/g, '-') // HH-MM-SS
  return `${prefix}_${date}_${time}.${extension}`
}

// Extract plain text from a MessageContent (string or multimodal parts)
export function extractTextFromContent(content: MessageContent): string {
  if (typeof content === 'string') return content
  return content
    .filter((part) => part.type === 'text')
    .map((part: any) => ('text' in part ? part.text : ''))
    .join(' ')
}

// Regex to match {{ACTION: ...}} tags used for tool execution descriptions
const ACTION_TAG_REGEX = /\{\{ACTION:\s*[^}]+\}\}/g

// Strip {{ACTION: ...}} tags from text content
// These tags are used internally for tool execution displays and should not be shown in regular message rendering
export function stripActionTags(text: string): string {
  return text.replace(ACTION_TAG_REGEX, '').trim()
}

// Build a single-chat responses text (assistant messages only)
export function buildChatResponsesText(messages: Message[]): string {
  const assistant = messages.filter((m) => m.role === 'assistant')
  return assistant.map((m) => extractTextFromContent(m.content)).join('\n\n---\n\n')
}

// Build a single-chat metadata array (assistant messages only)
export function buildChatMetadata(messages: Message[]): any[] {
  const assistant = messages.filter((m) => m.role === 'assistant')
  return assistant.map((m) => ({
    model: m.model,
    model_id: m.model_id,
    provider: m.provider,
    timestamp: m.timestamp,
    cost: m.cost,
    prompt_cost: m.prompt_cost,
    completion_cost: m.completion_cost,
    latency: m.latency,
    tokens: m.tokens,
  }))
}

// Build conversation-wide responses (grouped by model header)
export function buildConversationResponsesText(chats: Chat[]): string {
  return chats
    .map((chat) => {
      const responses = buildChatResponsesText(chat.messages)
      return `=== ${chat.model?.name || 'Unknown'} ===\n\n${responses}`
    })
    .join('\n\n---\n\n')
}

// Build conversation metadata (all messages, keeping roles)
export function buildConversationMetadata(chats: Chat[], syncMode: boolean) {
  return {
    timestamp: new Date().toISOString(),
    chats: chats.map((chat) => ({
      currentModel: chat.model?.name,
      currentModelId: chat.model?.model_id,
      currentProvider: chat.model?.provider,
      messages: chat.messages.map((m) => ({
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
        model: m.model,
        model_id: m.model_id,
        provider: m.provider,
        cost: m.cost,
        prompt_cost: m.prompt_cost,
        completion_cost: m.completion_cost,
        latency: m.latency,
        tokens: m.tokens,
        isError: m.isError,
      })),
    })),
    syncMode,
  }
}

