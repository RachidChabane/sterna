/**
 * CodeEditorModal Component
 *
 * Full-screen modal for IDE, isolated per user x chat.
 * Supports quick switching between chat workspaces in the same conversation.
 */

import { useState, useEffect, useMemo, Suspense, lazy } from 'react'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { X, Code2, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ModelIcon } from '@/components/models/ModelIcon'
import { cn } from '@/lib/utils'
import type { Model, Message, Chat } from '@/components/models/types'

// FullIDE pulls in @monaco-editor/react plus the full sandbox IDE UI
// (file tree, terminal, diff viewer, etc. — a ~156KB chunk). It's only
// needed once the IDE dialog is actually opened, so it's split into its
// own chunk and fetched on demand instead of shipping with the main bundle.
const FullIDE = lazy(() =>
  import('./FullIDE').then((module) => ({ default: module.FullIDE })),
)

function FullIDELoadingFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-accent-brand" />
        <p className="text-sm text-muted-foreground">Loading editor...</p>
      </div>
    </div>
  )
}

interface CodeEditorModalProps {
  userId?: string
  chatId?: string
  conversationId?: string
  model?: Model | null
  open: boolean
  onOpenChange: (open: boolean) => void
  messages?: Message[]
  // Optional: all chats for quick switcher
  chats?: Chat[]
}

export function CodeEditorModal({
  userId,
  chatId,
  conversationId,
  model,
  open,
  onOpenChange,
  messages,
  chats,
}: CodeEditorModalProps) {
  // Track active chat for quick switcher
  const [activeChatId, setActiveChatId] = useState(chatId)

  // Reset to provided chatId when modal opens or chatId prop changes
  useEffect(() => {
    if (open) {
      setActiveChatId(chatId)
    }
  }, [open, chatId])

  // Get active chat and model for display
  const activeChat = chats?.find(c => c.id === activeChatId)
  const activeModel = activeChat?.model || model
  const activeMessages = activeChat?.messages || messages

  // Determine if we should show the quick switcher (more than 1 chat)
  const showQuickSwitcher = chats && chats.length > 1

  // Detect mobile
  const [isMobile, setIsMobile] = useState(false)
  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)')
    setIsMobile(mediaQuery.matches)
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  // On mobile with multiple chats, hide model info and badge
  const showModelInfo = !isMobile || !showQuickSwitcher

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[98vw] w-[98vw] h-[95vh] !p-0 !gap-0"
        hideCloseButton
      >
        {/* Accessibility elements */}
        <DialogTitle className="sr-only">
          IDE - {model?.name || 'Code Editor'}
        </DialogTitle>
        <DialogDescription className="sr-only">
          Full-screen integrated development environment for code editing and execution
        </DialogDescription>

        {/* Header with quick switcher and close button */}
        <div className="relative flex items-center justify-between px-4 py-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 shrink-0 h-11">
          {/* Left: Current model info (hidden on mobile when multi-chat) */}
          <div className="flex items-center gap-2">
            {showModelInfo && (
              activeModel ? (
                <>
                  <ModelIcon
                    modelName={activeModel.name}
                    modelId={activeModel.model_id}
                    provider={activeModel.provider}
                    modelIconSlug={activeModel.model_icon_slug}
                    modelIconUrl={activeModel.model_icon_url}
                    providerIconSlug={activeModel.provider_icon_slug}
                    providerIconUrl={activeModel.provider_icon_url}
                    size={18}
                    showTooltip={false}
                  />
                  <span className="text-sm font-medium leading-none">{activeModel.name}</span>
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/20">
                    <Code2 className="h-2.5 w-2.5" />
                    IDE
                  </span>
                </>
              ) : (
                <>
                  <Code2 className="h-4 w-4" />
                  <span className="text-sm font-semibold leading-none">IDE</span>
                </>
              )
            )}
          </div>

          {/* Center: Quick switcher tabs (only if multiple chats) */}
          {showQuickSwitcher && (
            <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-1">
              {chats.map((chat) => {
                const isActive = chat.id === activeChatId

                return (
                  <TooltipProvider key={chat.id}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => setActiveChatId(chat.id)}
                          className={cn(
                            "relative flex items-center justify-center w-8 h-8 rounded-full transition-all",
                            isActive
                              ? "bg-accent text-accent-foreground"
                              : "hover:bg-muted text-muted-foreground hover:text-foreground"
                          )}
                        >
                          {chat.model ? (
                            <ModelIcon
                              modelName={chat.model.name}
                              modelId={chat.model.model_id}
                              provider={chat.model.provider}
                              modelIconSlug={chat.model.model_icon_slug}
                              modelIconUrl={chat.model.model_icon_url}
                              providerIconSlug={chat.model.provider_icon_slug}
                              providerIconUrl={chat.model.provider_icon_url}
                              size={18}
                              showTooltip={false}
                            />
                          ) : (
                            <div className="w-[18px] h-[18px] rounded-full bg-muted-foreground/30" />
                          )}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <div className="text-xs">
                          <div className="font-medium">{chat.model?.name || 'No model'}</div>
                          <div className="text-muted-foreground">Workspace</div>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )
              })}
            </div>
          )}

          {/* Right: Close button */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            className="h-7 w-7"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Full IDE */}
        <div className="flex-1 overflow-hidden">
          <Suspense fallback={<FullIDELoadingFallback />}>
            <FullIDE
              key={activeChatId} // Force remount when switching chats to reset state
              userId={userId}
              chatId={activeChatId}
              conversationId={conversationId}
              className="h-full"
              messages={activeMessages}
            />
          </Suspense>
        </div>
      </DialogContent>
    </Dialog>
  )
}
