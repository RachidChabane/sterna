/**
 * ConsigliereChat Component
 *
 * Simple chat interface for Consigliere modal.
 * Designed with clean flex architecture without Card wrapper to avoid height conflicts.
 */

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { SendIcon, UserIcon, BotIcon, Loader2Icon, Square } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { useAuthStore } from '@/store/authStore'
import type { Model, Message } from '@/components/models/types'
import { removeProviderPrefix } from '@/lib/model-utils'
import { Markdown } from '@/components/ui/markdown'
import { MarkdownTextarea } from '@/components/ui/MarkdownTextarea'
import { pricingUtils } from '@/lib/pricing-utils'
import { ModelIcon } from '@/components/models/ModelIcon'
import { extractTextFromContent, buildChatResponsesText, buildChatMetadata } from '@/utils/chatUtils'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { MessageActionMenus } from '@/components/models/MessageActionMenus'
import { MessageDetailsTooltip } from '@/components/models/MessageDetailsTooltip'

interface ConsigliereChatProps {
  model: Model | null
  messages: Message[]
  isLoading: boolean
  onSendMessage: (content: string) => void
  emptyStateContent?: React.ReactNode
  inputPlaceholder?: string
  onClearChat?: () => void
  isClearingChat?: boolean
  onOpenClearDialog?: () => void
  onCancel?: () => void
  canCancel?: boolean
  onRetry?: () => void
}

export function ConsigliereChat({
  model,
  messages,
  isLoading,
  onSendMessage,
  emptyStateContent,
  inputPlaceholder,
  onClearChat,
  isClearingChat = false,
  onOpenClearDialog,
  onCancel,
  canCancel,
  onRetry,
}: ConsigliereChatProps) {
  const [input, setInput] = useState('')
  const scrollAreaRef = useRef<HTMLDivElement>(null)
  const { toast } = useToast()
  const { user } = useAuthStore()

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = () => {
    if (input.trim() && !isLoading) {
      onSendMessage(input)
      setInput('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!isLoading && input.trim()) handleSend()
      return
    }
  }

  const formatCost = (cost?: number) => {
    return pricingUtils.formatCost(cost)
  }

  const formatLatency = (latency?: number) => {
    if (!latency) return 'N/A'
    if (latency < 1000) return `${latency}ms`
    return `${(latency / 1000).toFixed(1)}s`
  }

  // Copy / Export helpers (message-level)
  const copyMessageContent = (content: Message['content']) => {
    const text = extractTextFromContent(content)
    navigator.clipboard.writeText(text)
    toast({ title: 'Copied', description: 'Response copied to clipboard' })
  }

  const copyMessageMetadata = (message: Message) => {
    const metadata = {
      model: message.model,
      model_id: message.model_id,
      provider: message.provider,
      timestamp: message.timestamp,
      cost: message.cost,
      prompt_cost: message.prompt_cost,
      completion_cost: message.completion_cost,
      latency: message.latency,
      tokens: message.tokens,
    }
    navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
    toast({ title: 'Copied', description: 'Metadata copied to clipboard' })
  }

  const exportMessageContent = (content: Message['content'], model?: string) => {
    const text = extractTextFromContent(content)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `response-${model || 'unknown'}-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'Response exported as text file' })
  }

  const exportMessageMetadata = (message: Message) => {
    const metadata = {
      model: message.model,
      model_id: message.model_id,
      provider: message.provider,
      timestamp: message.timestamp,
      cost: message.cost,
      prompt_cost: message.prompt_cost,
      completion_cost: message.completion_cost,
      latency: message.latency,
      tokens: message.tokens,
    }
    const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `metadata-${message.model || 'unknown'}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'Metadata exported as JSON file' })
  }

  // Chat-level copy/export
  const copyChatResponses = () => {
    const text = buildChatResponsesText(messages)
    navigator.clipboard.writeText(text)
    toast({ title: 'Copied', description: 'All responses copied to clipboard' })
  }

  const copyChatMetadata = () => {
    const metadata = buildChatMetadata(messages)
    navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
    toast({ title: 'Copied', description: 'All metadata copied to clipboard' })
  }

  const exportChatResponses = () => {
    const text = buildChatResponsesText(messages)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `consigliere-chat-${model?.name || 'unknown'}-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'All responses exported' })
  }

  const exportChatMetadata = () => {
    const metadata = buildChatMetadata(messages)
    const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `consigliere-chat-metadata-${model?.name || 'unknown'}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'All metadata exported' })
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Messages Area */}
      <ScrollArea className="flex-1 px-4" ref={scrollAreaRef}>
          {messages.length === 0 ? (
            emptyStateContent || (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-12">
                {model ? (
                  <ModelIcon
                    modelName={model.name}
                    modelId={model.model_id}
                    provider={model.provider}
                    modelIconSlug={model.model_icon_slug}
                    modelIconUrl={model.model_icon_url}
                    providerIconSlug={model.provider_icon_slug}
                    providerIconUrl={model.provider_icon_url}
                    size={48}
                    showTooltip={false}
                    className="mb-2"
                  />
                ) : (
                  <BotIcon className="h-12 w-12 mb-2" />
                )}
                <p>No messages yet</p>
                <p className="text-xs mt-1">
                  {model
                    ? `Start a conversation with ${removeProviderPrefix(model.name, model.provider)}`
                    : 'Select a model to begin'}
                </p>
              </div>
            )
          ) : (
            <div className="space-y-4 py-4">
              {messages.map((message, index) => (
                <div
                  key={index}
                  className={cn(
                    'flex gap-3 animate-message-in',
                    message.role === 'user' && 'flex-row-reverse'
                  )}
                  style={{
                    animationDelay: `${index * 0.05}s`,
                  }}
                >
                  {message.role === 'user' ? (
                    <Avatar className="h-8 w-8">
                      {user?.avatar_url && (
                        <AvatarImage
                          src={user.avatar_url}
                          alt={`${user.first_name || ''} ${user.last_name || ''}`}
                        />
                      )}
                      <AvatarFallback>
                        <UserIcon className="h-4 w-4" />
                      </AvatarFallback>
                    </Avatar>
                  ) : (
                    <div className="w-8 h-8 flex items-center justify-center">
                      {message.model && message.model_id && message.provider ? (
                        <ModelIcon
                          modelName={message.model}
                          modelId={message.model_id}
                          provider={message.provider}
                          modelIconSlug={message.model_icon_slug}
                          modelIconUrl={message.model_icon_url}
                          providerIconSlug={message.provider_icon_slug}
                          providerIconUrl={message.provider_icon_url}
                          size={32}
                          showTooltip={false}
                        />
                      ) : (
                        <BotIcon className="h-8 w-8" />
                      )}
                    </div>
                  )}

                  <div
                    className={cn(
                      'flex-1 space-y-1',
                      message.role === 'user' && 'text-right'
                    )}
                  >
                    <div
                      className={cn(
                        'inline-block px-3 py-2 rounded-lg text-sm',
                        message.role === 'user'
                          ? 'bg-primary text-primary-foreground'
                          : message.isError
                          ? 'bg-destructive/10 text-destructive border border-destructive/20'
                          : 'bg-muted'
                      )}
                    >
                      <Markdown
                        className={cn(
                          '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
                          message.role === 'user' &&
                            'prose-p:text-primary-foreground/90 prose-strong:text-primary-foreground/90 prose-em:text-primary-foreground/90 prose-headings:text-primary-foreground/90 prose-li:text-primary-foreground/90',
                          message.role === 'assistant' &&
                            !message.isError &&
                            'prose-p:text-foreground/90 prose-li:text-foreground/90'
                        )}
                      >
                        {extractTextFromContent(message.content)}
                      </Markdown>
                    </div>

                    {message.role === 'assistant' && !message.isError && (
                      <div className="flex flex-wrap items-center gap-2 mt-2 text-xs">
                        {/* Details tooltip */}
                        <MessageDetailsTooltip
                          message={message}
                          messagesContainer={scrollAreaRef.current}
                          formatCost={formatCost}
                          formatLatency={formatLatency}
                          disabled={isLoading}
                        />

                        <MessageActionMenus
                          message={message}
                          onCopyContent={() => copyMessageContent(message.content)}
                          onCopyMetadata={() => copyMessageMetadata(message)}
                          onExportContent={() => exportMessageContent(message.content, message.model)}
                          onExportMetadata={() => exportMessageMetadata(message)}
                          showRetry={index === messages.findLastIndex(m => m.role === 'assistant')}
                          onRetry={onRetry}
                          disabled={isLoading}
                        />
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Loading indicator with thinking animation */}
          {isLoading && model && (
            <div className="flex items-center gap-3 px-4 py-4 border-t animate-in fade-in-50">
              <div className="w-8 h-8 flex items-center justify-center">
                <ModelIcon
                  modelName={model.name}
                  modelId={model.model_id}
                  provider={model.provider}
                  modelIconSlug={model.model_icon_slug}
                  modelIconUrl={model.model_icon_url}
                  providerIconSlug={model.provider_icon_slug}
                  providerIconUrl={model.provider_icon_url}
                  size={32}
                  showTooltip={false}
                />
              </div>
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <span>Thinking</span>
                <span className="flex gap-0.5">
                  <span
                    className="animate-bounce"
                    style={{ animationDelay: '0ms', animationDuration: '1s' }}
                  >
                    .
                  </span>
                  <span
                    className="animate-bounce"
                    style={{ animationDelay: '200ms', animationDuration: '1s' }}
                  >
                    .
                  </span>
                  <span
                    className="animate-bounce"
                    style={{ animationDelay: '400ms', animationDuration: '1s' }}
                  >
                    .
                  </span>
                </span>
              </div>
            </div>
          )}
      </ScrollArea>

      {/* Input Area (no chat-level copy/export here; matches /chats placement in header) */}
      <div className="p-4 border-t flex-shrink-0">
        <div className="flex flex-col gap-3">
          <MarkdownTextarea
            value={input}
            onChange={setInput}
            onKeyDown={handleKeyDown}
            placeholder={
              inputPlaceholder ||
              (model ? 'Ask for model recommendations...' : 'Select a model first')
            }
            className="w-full transition-all duration-200 max-h-[200px] border-0 focus:ring-0 bg-transparent"
            disabled={!model || isLoading}
            enableMarkdownRender={true}
          />
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {/* Left side intentionally empty to mirror /chats layout */}
            </div>
            <div className="flex items-center gap-2">
              {canCancel ? (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-block">
                        <Button
                          size="icon"
                          variant="outline"
                          onClick={onCancel}
                          className="h-9 w-9 rounded-full transition-all duration-200 hover:scale-105 hover:shadow-md bg-destructive/10 border border-destructive/30 hover:bg-destructive/20"
                        >
                          <Square className="h-4 w-4 text-destructive" />
                        </Button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>Stop</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="inline-block">
                        <Button
                          size="icon"
                          onClick={handleSend}
                          disabled={!model || !input.trim() || isLoading}
                          className="h-9 w-9 rounded-full transition-all duration-200 hover:scale-105 hover:shadow-lg disabled:opacity-50 disabled:hover:scale-100"
                        >
                          <SendIcon className="h-4 w-4" />
                        </Button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p>{!model ? 'Select a model first' : !input.trim() ? 'Enter a message' : 'Send'}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
