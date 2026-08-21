import { useEffect, useRef } from 'react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { User, Bot } from 'lucide-react'
import type { VoiceRoomMessage, VoiceAgent } from '@/types/voiceRoom'
import { cn } from '@/lib/utils'
import { ModelIcon } from '@/components/models/ModelIcon'
import useModelStore from '@/store/modelStore'

interface ConversationViewProps {
  messages: VoiceRoomMessage[]
  agents: VoiceAgent[]
  currentTranscript: string
  isListening: boolean
}

export function ConversationView({
  messages,
  agents,
  currentTranscript,
  isListening,
}: ConversationViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { allModels } = useModelStore()

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages, currentTranscript])

  const getAgentModel = (agentId: string) => {
    const agent = agents.find((a) => a.id === agentId)
    if (!agent?.model_id) return undefined
    return allModels.find((m) => m.model_id === agent.model_id)
  }

  const getAgentInfo = (agentId: string) => {
    return agents.find((a) => a.id === agentId)
  }

  if (messages.length === 0 && !currentTranscript) {
    return (
      <div className="flex items-center justify-center h-full text-center">
        <div className="max-w-md">
          <div className="p-4 bg-muted/50 rounded-full w-20 h-20 mx-auto mb-4 flex items-center justify-center">
            <Bot className="h-10 w-10 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-medium mb-2">Ready to Chat</h3>
          <p className="text-muted-foreground">
            Press the microphone button and start speaking. The AI agents will
            respond in order.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="space-y-4 pb-4">
      {messages.map((message) => {
        const agent = message.agent_id ? getAgentInfo(message.agent_id) : undefined
        const model = message.agent_id ? getAgentModel(message.agent_id) : undefined

        return (
        <div
          key={message.id}
          className={cn(
            'flex gap-3',
            message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
          )}
        >
          {/* Avatar */}
          {message.role === 'user' ? (
            <Avatar className="h-8 w-8 flex-shrink-0 bg-primary">
              <AvatarFallback className="bg-primary text-primary-foreground text-xs">
                <User className="h-4 w-4" />
              </AvatarFallback>
            </Avatar>
          ) : (
            <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
              <ModelIcon
                modelName={model?.name || message.agent_name || 'Assistant'}
                modelId={agent?.model_id || ''}
                provider={model?.provider || ''}
                modelIconSlug={model?.model_icon_slug}
                modelIconUrl={model?.model_icon_url}
                providerIconSlug={model?.provider_icon_slug}
                providerIconUrl={model?.provider_icon_url}
                size={32}
                showTooltip={false}
              />
            </div>
          )}

          {/* Message content */}
          <div
            className={cn(
              'max-w-[80%]',
              message.role === 'user' ? 'text-right' : 'text-left'
            )}
          >
            {/* Agent name */}
            {message.role === 'assistant' && message.agent_name && (
              <div className="text-xs text-muted-foreground mb-1">
                {message.agent_name}
              </div>
            )}

            {/* Bubble */}
            <div
              className={cn(
                'inline-block px-4 py-2 rounded-2xl',
                message.role === 'user'
                  ? 'bg-primary text-primary-foreground rounded-tr-sm'
                  : 'bg-muted rounded-tl-sm'
              )}
            >
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
            </div>

            {/* Timestamp */}
            <div className="text-xs text-muted-foreground mt-1">
              {new Date(message.created_at).toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </div>
          </div>
        </div>
        )
      })}

      {/* Live transcript */}
      {currentTranscript && (
        <div className="flex gap-3">
          <Avatar className="h-8 w-8 flex-shrink-0 bg-primary">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs">
              <User className="h-4 w-4" />
            </AvatarFallback>
          </Avatar>
          <div className="max-w-[80%]">
            <div
              className={cn(
                'inline-block px-4 py-2 rounded-2xl bg-primary/20 text-foreground rounded-tr-sm',
                isListening && 'animate-pulse'
              )}
            >
              <p className="text-sm italic">{currentTranscript}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
