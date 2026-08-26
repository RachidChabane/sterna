/**
 * FileDetailsModal Component
 *
 * Displays detailed information about a file including:
 * - Model that created the file
 * - Model that last modified the file
 * - Link to the message that created the file
 * - Timestamps
 */

import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogHeader } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { ModelIcon } from '@/components/models/ModelIcon'
import { Loader2, FileText, Clock, User, AlertCircle, Eye } from 'lucide-react'
import { cn } from '@/lib/utils'
import { fsAPI, type FileMetadata } from '@/api/fs'
import { useAuthStore } from '@/store/authStore'
import { toErrorMessage } from '@/utils/errorMessages'

interface FileDetailsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  filePath: string
  fileName: string
  userId?: string
  conversationId?: string
  chatId?: string
  onNavigateToMessage?: (messageId: string) => void
}

export function FileDetailsModal({
  open,
  onOpenChange,
  filePath,
  fileName,
  userId,
  conversationId,
  chatId,
  onNavigateToMessage
}: FileDetailsModalProps) {
  const [metadata, setMetadata] = useState<FileMetadata | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [avatarError, setAvatarError] = useState(false)
  const { user } = useAuthStore()

  useEffect(() => {
    if (open && userId && conversationId) {
      loadMetadata()
    }
  }, [open, filePath, userId, conversationId])

  // Reset avatar error when user changes
  useEffect(() => {
    setAvatarError(false)
  }, [user?.avatar_url])

  const loadMetadata = async () => {
    if (!userId || !conversationId) return

    setIsLoading(true)
    setError(null)

    try {
      const result = await fsAPI.getFileMetadata({
        user_id: userId,
        conversation_id: conversationId,
        chat_id: chatId,
        path: filePath,
      })

      if (result.success && result.metadata) {
        setMetadata(result.metadata)
      } else {
        setError(result.error || 'Failed to load metadata')
      }
    } catch (err) {
      console.error('Failed to load file metadata:', err)
      setError(toErrorMessage(err) || 'Failed to load metadata')
    } finally {
      setIsLoading(false)
    }
  }

  const formatTimestamp = (timestamp?: string | number) => {
    if (!timestamp) return 'Unknown'
    try {
      // Convert Unix timestamp (seconds) to Date
      // Backend sends timestamps as Unix timestamps (seconds since epoch)
      const timestampNum = typeof timestamp === 'string' ? parseFloat(timestamp) : timestamp
      const date = new Date(timestampNum * 1000) // Convert seconds to milliseconds

      if (isNaN(date.getTime())) {
        return 'Invalid date'
      }

      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return timestamp?.toString() || 'Invalid date'
    }
  }

  const formatFileSize = (bytes?: number) => {
    if (bytes === undefined) return 'Unknown'
    if (bytes === 0) return '0 Bytes'

    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // Render avatar/icon for creator or modifier
  const renderAuthorAvatar = (author?: FileMetadata['created_by']) => {
    if (!author) {
      // Manual creation/modification by user
      return (
        <>
          {user?.avatar_url && !avatarError ? (
            <img
              src={user.avatar_url}
              alt={`${user.first_name} ${user.last_name}`}
              className="h-5 w-5 rounded-full object-cover flex-shrink-0"
              crossOrigin="anonymous"
              onError={() => setAvatarError(true)}
            />
          ) : (
            <div className="h-5 w-5 rounded-full gradient-primary flex items-center justify-center flex-shrink-0">
              <User className="h-3 w-3 text-white" />
            </div>
          )}
        </>
      )
    }

    // AI model
    return (
      <ModelIcon
        modelName={author.model_name}
        modelId={author.model_id}
        provider={author.provider}
        modelIconSlug={author.model_icon_slug}
        modelIconUrl={author.model_icon_url}
        providerIconSlug={author.provider_icon_slug || author.provider?.toLowerCase()}
        providerIconUrl={author.provider_icon_url}
        size={20}
        showTooltip={false}
      />
    )
  }

  const renderAuthorName = (author?: FileMetadata['created_by']) => {
    if (!author) {
      return 'You'
    }
    return author.model_name.split('/').pop()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader className="pb-4 border-b">
          <DialogTitle className="flex items-center gap-2 text-lg">
            <FileText className="h-5 w-5 text-primary" />
            File Details
          </DialogTitle>
          <DialogDescription className="text-sm mt-1">
            {fileName}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-5">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Loading file details...</p>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-3 p-4 rounded-lg bg-destructive/10 border border-destructive/30 shadow-sm">
              <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-sm font-semibold text-destructive">Error Loading File Details</p>
                <p className="text-xs text-destructive/80 mt-1.5">{error}</p>
              </div>
            </div>
          )}

          {!isLoading && !error && metadata && (
            <>
              {/* Created by */}
              <div className="space-y-3">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5" />
                  Created By
                </label>
                <div className="flex items-center justify-between p-4 rounded-lg border bg-gradient-to-br from-muted/40 to-muted/20 shadow-sm hover:shadow-md transition-shadow">
                  <div className="flex items-center gap-3">
                    <div className="flex-shrink-0">
                      {renderAuthorAvatar(metadata.created_by)}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold truncate">
                        {renderAuthorName(metadata.created_by)}
                      </p>
                      {(metadata.created_by?.timestamp || metadata.created_at) && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {formatTimestamp(metadata.created_by?.timestamp || metadata.created_at)}
                        </p>
                      )}
                    </div>
                  </div>
                  {metadata.created_by?.message_id && onNavigateToMessage && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 gap-1.5 ml-3 flex-shrink-0"
                      onClick={() => {
                        if (metadata.created_by?.message_id) {
                          onNavigateToMessage(metadata.created_by.message_id)
                        }
                      }}
                    >
                      <Eye className="h-3 w-3" />
                      <span className="text-xs">View Message</span>
                    </Button>
                  )}
                </div>
              </div>

              {/* Last modified by - show if there's a modification (either by AI or manual) */}
              {(() => {
                // Check if file was modified after the last AI modification
                const modifiedAt = metadata.modified_at ? parseFloat(metadata.modified_at.toString()) : 0
                const modifiedByTimestamp = metadata.modified_by?.timestamp
                  ? (typeof metadata.modified_by.timestamp === 'string'
                      ? parseFloat(metadata.modified_by.timestamp)
                      : metadata.modified_by.timestamp)
                  : 0

                // If modified_at is more recent than modified_by timestamp, it's a manual modification
                const isManualModification = modifiedAt > modifiedByTimestamp
                const showModifiedBy = isManualModification ? undefined : metadata.modified_by

                // Only show if there's been a modification after creation
                const createdByTimestamp = metadata.created_by?.timestamp
                  ? (typeof metadata.created_by.timestamp === 'string'
                      ? parseFloat(metadata.created_by.timestamp)
                      : metadata.created_by.timestamp)
                  : (metadata.created_at
                      ? parseFloat(metadata.created_at.toString())
                      : 0)

                const hasModification = modifiedAt > createdByTimestamp

                if (!hasModification) return null

                return (
                  <div className="space-y-3">
                    <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      Last Modified By
                    </label>
                    <div className="flex items-center justify-between p-4 rounded-lg border bg-gradient-to-br from-muted/40 to-muted/20 shadow-sm hover:shadow-md transition-shadow">
                      <div className="flex items-center gap-3">
                        <div className="flex-shrink-0">
                          {renderAuthorAvatar(showModifiedBy)}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold truncate">
                            {renderAuthorName(showModifiedBy)}
                          </p>
                          {(showModifiedBy?.timestamp || metadata.modified_at) && (
                            <p className="text-xs text-muted-foreground mt-0.5">
                              {formatTimestamp(showModifiedBy?.timestamp || metadata.modified_at)}
                            </p>
                          )}
                        </div>
                      </div>
                      {showModifiedBy?.message_id && onNavigateToMessage && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 gap-1.5 ml-3 flex-shrink-0"
                          onClick={() => {
                            if (showModifiedBy?.message_id) {
                              onNavigateToMessage(showModifiedBy.message_id)
                            }
                          }}
                        >
                          <Eye className="h-3 w-3" />
                          <span className="text-xs">View Message</span>
                        </Button>
                      )}
                    </div>
                  </div>
                )
              })()}

            </>
          )}

          {!isLoading && !error && !metadata && (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <FileText className="h-12 w-12 text-muted-foreground/30" />
              <p className="text-sm font-medium text-muted-foreground">No metadata available</p>
              <p className="text-xs text-muted-foreground/70">This file has no tracking information</p>
            </div>
          )}
        </div>

        {/* Footer with file info */}
        <div className="flex items-baseline gap-3 text-xs text-muted-foreground pt-3 border-t bg-muted/20 px-6 py-3 -mx-6 -mb-6 rounded-b-lg">
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            <span className="font-medium shrink-0">Path:</span>
            <span className="font-mono truncate">{filePath}</span>
          </div>
          {!isLoading && !error && metadata && metadata.size !== undefined && (
            <div className="flex items-center gap-1.5 shrink-0">
              <span className="font-medium">Size:</span>
              <span className="font-mono">{formatFileSize(metadata.size)}</span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
