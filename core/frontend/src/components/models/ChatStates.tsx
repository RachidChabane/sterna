/**
 * ChatStates Component
 *
 * Manages various chat states:
 * - Loading indicator with "Thinking..." animation
 * - Interrupted response warning
 * - Empty state (suggested questions or placeholder)
 */

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ModelIcon } from './ModelIcon'
import { SuggestedQuestions } from './SuggestedQuestions'
import { BotIcon, KeyRound, SendIcon, X } from 'lucide-react'
import { removeProviderPrefix } from '@/lib/model-utils'
import { extractTextFromContent } from '@/utils/chatUtils'
import { useSettingsStore } from '@/store/settingsStore'
import type { Model, Message } from './types'

interface ChatStatesProps {
  // Empty state
  messages: Message[]
  emptyStateContent?: React.ReactNode
  syncMode: boolean
  model: Model | null
  onSuggestionClick?: (suggestion: string) => void

  // Loading state
  isLoading: boolean
  canCancel?: boolean
  onCancel?: () => void
  onOpenModelDetails: (modelId?: string) => void

  // Interrupted response warning
  suppressInterruptedWarning: boolean
  onResend: (message: string) => void
}

export function ChatStates({
  messages,
  emptyStateContent,
  syncMode,
  model,
  onSuggestionClick,
  isLoading,
  canCancel,
  onCancel,
  onOpenModelDetails,
  suppressInterruptedWarning,
  onResend,
}: ChatStatesProps) {
  // Get the last message for error checking
  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null

  // Determine if we should show the interrupted warning
  // Show if: last message is from user (waiting for response)
  // OR last message is assistant with error/interrupted
  const showInterruptedWarning =
    !isLoading &&
    !suppressInterruptedWarning &&
    messages.length > 0 &&
    model &&
    (lastMessage?.role === 'user' ||
     (lastMessage?.role === 'assistant' &&
      (lastMessage?.error ||
       (lastMessage?.is_interrupted && !lastMessage?.is_stopped))))

  // Get error message from assistant message if available
  const errorMessage = lastMessage?.role === 'assistant' ? lastMessage?.error : null
  // Actionable key-related errors get a direct-resolution button instead
  // of only a dead-end resend.
  const errorCode = lastMessage?.role === 'assistant' ? lastMessage?.errorCode : undefined
  const isKeyError =
    errorCode === 'no_api_key' ||
    errorCode === 'invalid_api_key' ||
    errorCode === 'insufficient_credits'

  return (
    <>
      {/* Empty State */}
      {messages.length === 0 && (
        <>
          {emptyStateContent ? (
            emptyStateContent
          ) : !syncMode ? (
            <SuggestedQuestions onSuggestionClick={onSuggestionClick || (() => {})} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
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
                {model ? `Start a conversation with ${removeProviderPrefix(model.name, model.provider)}` : 'Select a model to begin'}
              </p>
            </div>
          )}
        </>
      )}

      {/* Warning for interrupted response or error */}
      {showInterruptedWarning && (
        <div className="mx-4 mt-4 mb-2 p-3 rounded-lg border border-border/50 bg-muted/30 animate-in fade-in-50">
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-xs text-muted-foreground mb-2.5">
                {errorMessage || 'The response was interrupted. Click below to try again.'}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {isKeyError && (
                  <Button
                    size="sm"
                    variant="default"
                    className="h-7 text-xs px-3"
                    onClick={() => useSettingsStore.getState().openSettings('apikey')}
                  >
                    <KeyRound className="h-3 w-3 mr-1.5" />
                    {errorCode === 'no_api_key' ? 'Add an API key' : 'Check API key settings'}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs px-3 border-border/60 hover:bg-muted/50"
                  onClick={() => {
                    // Find the last user message (may be second-to-last if assistant errored)
                    const lastUserMessage = [...messages].reverse().find(m => m.role === 'user')
                    if (lastUserMessage) {
                      onResend(extractTextFromContent(lastUserMessage.content))
                    }
                  }}
                  disabled={isLoading}
                >
                  <SendIcon className="h-3 w-3 mr-1.5" />
                  Resend Message
                </Button>
              </div>
              {errorCode === 'no_api_key' && (
                <p className="text-[11px] text-muted-foreground mt-2">
                  Your key stays yours — requests are billed by your provider, not by us.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Loading indicator — animated model icon */}
      {isLoading && model && (
        <div className="flex items-center gap-2 md:gap-3 mt-4 animate-in fade-in-50">
          <div className="w-8 h-8 flex items-center justify-center relative">
            <button
              type="button"
              className="p-0 m-0 inline-flex items-center justify-center rounded hover:opacity-90 focus:outline-none streaming-icon-breathe"
              onClick={() => onOpenModelDetails(model?.model_id)}
              title={model?.name}
            >
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
            </button>
          </div>
          {canCancel && (
            <Button
              variant="outline"
              size="sm"
              onClick={onCancel}
              className="h-7 px-2 py-1"
            >
              <X className="h-4 w-4" />
              <span className="ml-1 text-xs">Stop</span>
            </Button>
          )}
        </div>
      )}
    </>
  )
}
