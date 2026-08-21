/**
 * MessageViewModal Component
 *
 * Displays the full content of a message by its ID.
 * Used to show which message created or modified a file.
 */

import { Dialog, DialogContent, DialogTitle, DialogHeader, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { X, MessageSquare } from 'lucide-react'
import { Markdown } from '@/components/ui/markdown'
import { ModelIcon } from '@/components/models/ModelIcon'
import type { Message } from '@/components/models/types'

interface MessageViewModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  message: Message | null
  isLoading?: boolean
}

export function MessageViewModal({
  open,
  onOpenChange,
  message,
  isLoading = false
}: MessageViewModalProps) {
  if (!message && !isLoading) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col">
        <DialogHeader className="pb-4 border-b">
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-primary" />
            Message Details
          </DialogTitle>
          {message && (
            <DialogDescription className="flex items-center gap-2 mt-2">
              {message.model && (
                <div className="flex items-center gap-2">
                  <ModelIcon
                    modelName={message.model}
                    modelId={message.model_id || ''}
                    provider={message.provider || ''}
                    modelIconSlug={message.model_icon_slug}
                    modelIconUrl={message.model_icon_url}
                    providerIconSlug={message.provider_icon_slug}
                    providerIconUrl={message.provider_icon_url}
                    size={20}
                    showTooltip={false}
                  />
                  <span className="text-sm font-medium">{message.model}</span>
                </div>
              )}
            </DialogDescription>
          )}
        </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4">
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
                <p className="text-sm text-muted-foreground">Loading message...</p>
              </div>
            </div>
          )}

          {!isLoading && message && (
            <div className="space-y-4">
              {/* Message Content */}
              <div className="prose prose-sm dark:prose-invert max-w-none">
                {typeof message.content === 'string' ? (
                  <Markdown>{message.content}</Markdown>
                ) : (
                  <div>
                    {Array.isArray(message.content) ? (
                      message.content.map((part, idx) => (
                        <div key={idx}>
                          {part.type === 'text' && <Markdown>{part.text}</Markdown>}
                          {part.type === 'image_url' && (
                            <img
                              src={part.image_url.url}
                              alt="Message attachment"
                              className="max-w-full h-auto rounded-lg my-4"
                            />
                          )}
                        </div>
                      ))
                    ) : (
                      <p className="text-muted-foreground">No content available</p>
                    )}
                  </div>
                )}
              </div>

              {/* Message Metadata */}
              <div className="mt-6 pt-4 border-t grid grid-cols-2 gap-4 text-sm">
                {message.timestamp && (
                  <div>
                    <span className="font-medium text-muted-foreground">Time:</span>
                    <span className="ml-2">{new Date(message.timestamp).toLocaleString()}</span>
                  </div>
                )}
                {message.tokens && (
                  <div>
                    <span className="font-medium text-muted-foreground">Tokens:</span>
                    <span className="ml-2">
                      {message.tokens.prompt} + {message.tokens.completion} = {(message.tokens.prompt || 0) + (message.tokens.completion || 0)}
                    </span>
                  </div>
                )}
                {message.cost !== undefined && (
                  <div>
                    <span className="font-medium text-muted-foreground">Cost:</span>
                    <span className="ml-2">${message.cost.toFixed(6)}</span>
                  </div>
                )}
                {message.latency && (
                  <div>
                    <span className="font-medium text-muted-foreground">Latency:</span>
                    <span className="ml-2">{message.latency.toFixed(2)}s</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {!isLoading && !message && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <MessageSquare className="h-12 w-12 text-muted-foreground/30 mb-4" />
              <p className="text-sm font-medium text-muted-foreground">Message not found</p>
              <p className="text-xs text-muted-foreground/70 mt-1">
                This message may have been deleted or is no longer available
              </p>
            </div>
          )}
        </div>

        <div className="pt-4 border-t flex justify-end">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
