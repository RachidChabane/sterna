/**
 * TranscriptDrawer - Displays voice room conversation transcript
 *
 * Shows the conversation in a similar format to the chats page,
 * with proper icons, avatars, and action buttons.
 */

import { useMemo, useEffect, useRef } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { UserIcon, MoreHorizontal, FileText, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Markdown } from '@/components/ui/markdown'
import { ModelIcon } from '@/components/models/ModelIcon'
import { useToast } from '@/hooks/use-toast'
import useModelStore from '@/store/modelStore'
import { useAuthStore } from '@/store/authStore'
import type { User } from '@/api/hand-written/rest'
import type { VoiceRoomMessage, VoiceAgent } from '@/types/voiceRoom'
import type { Model } from '@/components/models/types'

interface TranscriptDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  messages: VoiceRoomMessage[]
  agents: VoiceAgent[]
  roomName: string
  onViewModelDetails?: (modelId: string) => void
  streamingMessage?: {
    agent_id: string
    agent_name: string
    content: string
  } | null
  thinkingAgentId?: string
}

interface TranscriptMessageData {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  agentName?: string
  modelId?: string
  model?: Model
}

// Convert VoiceRoomMessage to display format
function convertToDisplayMessage(
  voiceMessage: VoiceRoomMessage,
  agents: VoiceAgent[],
  allModels: Model[]
): TranscriptMessageData {
  const agent = voiceMessage.agent_id
    ? agents.find((a) => a.id === voiceMessage.agent_id)
    : undefined

  // Look up full model info from store
  const model = agent?.model_id
    ? allModels.find(m => m.model_id === agent.model_id)
    : undefined

  return {
    id: voiceMessage.id,
    role: voiceMessage.role,
    content: voiceMessage.content || '',
    timestamp: new Date(voiceMessage.created_at),
    agentName: agent?.display_name || voiceMessage.agent_name,
    modelId: agent?.model_id,
    model,
  }
}

export function TranscriptDrawer({
  open,
  onOpenChange,
  messages,
  agents,
  roomName,
  onViewModelDetails,
  streamingMessage,
  thinkingAgentId,
}: TranscriptDrawerProps) {
  const { toast } = useToast()
  const { allModels } = useModelStore()
  const { user } = useAuthStore()

  // Convert voice messages to display format
  const displayMessages = useMemo(
    () => messages.map((m) => convertToDisplayMessage(m, agents, allModels)),
    [messages, agents, allModels]
  )

  // Auto-scroll to bottom when streaming message updates
  const scrollRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (streamingMessage && scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [streamingMessage?.content])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        className="w-full sm:max-w-lg md:max-w-xl lg:max-w-2xl flex flex-col p-0 border-0 bg-background"
      >
        {/* Header */}
        <SheetHeader className="px-6 py-5 border-b border-border">
          <SheetTitle className="text-sm font-medium tracking-wider uppercase text-foreground/70">
            Transcript
          </SheetTitle>
          <p className="text-xs text-muted-foreground">
            {roomName} - {displayMessages.length} messages
          </p>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-5 py-4 space-y-5">
            {displayMessages.length === 0 && !streamingMessage ? (
              <div className="text-center py-16 text-sm text-muted-foreground">
                No messages yet. Start speaking to begin the conversation.
              </div>
            ) : (
              <>
                {displayMessages.map((message) => (
                  <TranscriptMessage
                    key={message.id}
                    message={message}
                    user={user}
                    onCopy={() => {
                      navigator.clipboard.writeText(message.content)
                      toast({ title: 'Copied to clipboard' })
                    }}
                    onViewModelDetails={onViewModelDetails}
                  />
                ))}
                {/* Streaming message */}
                {streamingMessage && (
                  <div ref={scrollRef}>
                    <StreamingMessage
                      agentName={streamingMessage.agent_name}
                      content={streamingMessage.content}
                      agentId={streamingMessage.agent_id}
                      agents={agents}
                      allModels={allModels}
                      onViewModelDetails={onViewModelDetails}
                    />
                  </div>
                )}
                {/* Thinking indicator */}
                {thinkingAgentId && !streamingMessage && (
                  <div ref={scrollRef}>
                    <ThinkingMessage
                      agentId={thinkingAgentId}
                      agents={agents}
                      allModels={allModels}
                      onViewModelDetails={onViewModelDetails}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}

// Individual message component
function TranscriptMessage({
  message,
  user,
  onCopy,
  onViewModelDetails,
}: {
  message: TranscriptMessageData
  user: User | null
  onCopy: () => void
  onViewModelDetails?: (modelId: string) => void
}) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex gap-3 group',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      {isUser ? (
        <Avatar className="h-8 w-8 shrink-0 bg-muted">
          {user?.avatar_url && (
            <AvatarImage
              src={user.avatar_url}
              alt={`${user.first_name || ''} ${user.last_name || ''}`}
            />
          )}
          <AvatarFallback className="bg-muted text-muted-foreground">
            <UserIcon className="h-4 w-4" />
          </AvatarFallback>
        </Avatar>
      ) : (
        <div className="w-8 h-8 flex items-center justify-center shrink-0">
          {message.model && message.modelId ? (
            <button
              type="button"
              className="p-0 m-0 inline-flex items-center justify-center rounded hover:opacity-90 focus:outline-none"
              onClick={() => onViewModelDetails?.(message.modelId!)}
              title={message.model.name}
            >
              <ModelIcon
                modelName={message.model.name}
                modelId={message.modelId}
                provider={message.model.provider}
                modelIconSlug={message.model.model_icon_slug}
                modelIconUrl={message.model.model_icon_url}
                providerIconSlug={message.model.provider_icon_slug}
                providerIconUrl={message.model.provider_icon_url}
                size={28}
                showTooltip={false}
              />
            </button>
          ) : (
            <ModelIcon
              modelName={message.agentName || 'Assistant'}
              modelId=""
              provider=""
              size={28}
              showTooltip={false}
            />
          )}
        </div>
      )}

      {/* Message content */}
      <div
        className={cn(
          'flex flex-col max-w-[85%] min-w-0',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        {/* Name and time */}
        <div
          className={cn(
            'flex items-center gap-2 mb-1.5',
            isUser ? 'flex-row-reverse' : 'flex-row'
          )}
        >
          <span className="text-xs font-medium text-foreground/70">
            {isUser ? 'You' : message.agentName || 'Assistant'}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {message.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>

        {/* Content bubble */}
        <div
          className={cn(
            'rounded-2xl px-4 py-2.5',
            isUser
              ? 'bg-primary/15 text-foreground rounded-tr-sm border border-primary/20'
              : 'bg-card text-foreground rounded-tl-sm'
          )}
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap">{String(message.content ?? '')}</p>
          ) : (
            <div className={cn(
              'prose prose-sm max-w-none',
              'prose-p:text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-code:text-primary'
            )}>
              <Markdown>{String(message.content ?? '')}</Markdown>
            </div>
          )}
        </div>

        {/* Actions for assistant messages */}
        {!isUser && (
          <div className="flex items-center gap-1 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted"
                >
                  <MoreHorizontal className="h-3 w-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                className="bg-card border-border text-foreground"
              >
                <DropdownMenuItem
                  onClick={onCopy}
                  className="hover:bg-muted focus:bg-muted"
                >
                  <Copy className="h-3.5 w-3.5 mr-2" />
                  Copy message
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="hover:bg-muted focus:bg-muted"
                  onClick={() => {
                    const blob = new Blob([message.content], { type: 'text/plain' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `message_${message.timestamp.toISOString()}.txt`
                    a.click()
                    URL.revokeObjectURL(url)
                  }}
                >
                  <FileText className="h-3.5 w-3.5 mr-2" />
                  Export as text
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
    </div>
  )
}

// Streaming message component with typing indicator
function StreamingMessage({
  agentName,
  content,
  agentId,
  agents,
  allModels,
  onViewModelDetails,
}: {
  agentName: string
  content: string
  agentId: string
  agents: VoiceAgent[]
  allModels: Model[]
  onViewModelDetails?: (modelId: string) => void
}) {
  const agent = agents.find((a) => a.id === agentId)
  const model = agent?.model_id
    ? allModels.find((m) => m.model_id === agent.model_id)
    : undefined

  return (
    <div className="flex gap-3 flex-row">
      {/* Avatar */}
      <div className="w-8 h-8 flex items-center justify-center shrink-0">
        {model && agent?.model_id ? (
          <button
            type="button"
            className="p-0 m-0 inline-flex items-center justify-center rounded hover:opacity-90 focus:outline-none"
            onClick={() => onViewModelDetails?.(agent.model_id)}
            title={model.name}
          >
            <ModelIcon
              modelName={model.name}
              modelId={agent.model_id}
              provider={model.provider}
              modelIconSlug={model.model_icon_slug}
              modelIconUrl={model.model_icon_url}
              providerIconSlug={model.provider_icon_slug}
              providerIconUrl={model.provider_icon_url}
              size={28}
              showTooltip={false}
            />
          </button>
        ) : (
          <ModelIcon
            modelName={agentName}
            modelId=""
            provider=""
            size={28}
            showTooltip={false}
          />
        )}
      </div>

      {/* Message content */}
      <div className="flex flex-col max-w-[85%] min-w-0 items-start">
        {/* Name */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-medium text-foreground/70">
            {agentName}
          </span>
          <span className="text-[10px] text-muted-foreground">
            typing...
          </span>
        </div>

        {/* Content bubble */}
        <div className="rounded-2xl px-4 py-2.5 rounded-tl-sm bg-card">
          <div className="prose prose-sm max-w-none prose-p:text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-code:text-primary">
            <Markdown>{content || ''}</Markdown>
            <span className="inline-block w-1.5 h-4 animate-pulse ml-0.5 rounded-sm bg-muted-foreground" />
          </div>
        </div>
      </div>
    </div>
  )
}

// Thinking indicator component (shown before text starts streaming)
function ThinkingMessage({
  agentId,
  agents,
  allModels,
  onViewModelDetails,
}: {
  agentId: string
  agents: VoiceAgent[]
  allModels: Model[]
  onViewModelDetails?: (modelId: string) => void
}) {
  const agent = agents.find((a) => a.id === agentId)
  const model = agent?.model_id
    ? allModels.find((m) => m.model_id === agent.model_id)
    : undefined
  const agentName = agent?.display_name || 'Assistant'

  return (
    <div className="flex gap-3 flex-row">
      {/* Avatar */}
      <div className="w-8 h-8 flex items-center justify-center shrink-0">
        {model && agent?.model_id ? (
          <button
            type="button"
            className="p-0 m-0 inline-flex items-center justify-center rounded hover:opacity-90 focus:outline-none"
            onClick={() => onViewModelDetails?.(agent.model_id)}
            title={model.name}
          >
            <ModelIcon
              modelName={model.name}
              modelId={agent.model_id}
              provider={model.provider}
              modelIconSlug={model.model_icon_slug}
              modelIconUrl={model.model_icon_url}
              providerIconSlug={model.provider_icon_slug}
              providerIconUrl={model.provider_icon_url}
              size={28}
              showTooltip={false}
            />
          </button>
        ) : (
          <ModelIcon
            modelName={agentName}
            modelId=""
            provider=""
            size={28}
            showTooltip={false}
          />
        )}
      </div>

      {/* Thinking content */}
      <div className="flex flex-col max-w-[85%] min-w-0 items-start">
        {/* Name */}
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-medium text-foreground/70">
            {agentName}
          </span>
        </div>

        {/* Thinking bubble with animated dots */}
        <div className="rounded-2xl px-4 py-2.5 rounded-tl-sm bg-card">
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">Thinking</span>
            <span className="flex gap-0.5">
              <span className="w-1 h-1 rounded-full bg-muted-foreground/60 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/60 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 rounded-full bg-muted-foreground/60 animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
