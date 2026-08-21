/**
 * ChatGridCard Component
 *
 * A simplified chat card for the grid comparison view.
 * Shows only header with model selector and scrollable message area.
 * Input is shared at the grid level, not per card.
 */

import { memo, useCallback, useMemo, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubTrigger,
  DropdownMenuSubContent,
} from '@/components/ui/dropdown-menu'
import {
  X,
  Loader2,
  MessageSquare,
  MoreVertical,
  ScrollText,
  Copy,
  Download,
  FileText,
  Braces,
  BookOpen,
} from 'lucide-react'
import { ModelComboBox } from './ModelComboBox'
import { ModelIcon } from './ModelIcon'
import { MessageList } from './MessageList'
import { ChatPanelProvider } from './ChatPanelContext'
import { SparkAutoFixProvider, type SparkFixRequest } from './SparkAutoFixContext'
import { FilePreviewModal } from './FilePreviewModal'
import { PdfPreviewModal } from './PdfPreviewModal'
import { ImagePreviewModal } from './ImagePreviewModal'
import { pricingUtils } from '@/lib/pricing-utils'
import { useAuthStore } from '@/store/authStore'
import { assetsAPI } from '@/api/assets'
import { useToast } from '@/hooks/use-toast'
import { formatLatencyFromSeconds } from '@/utils/latency'
import type { Chat, Model, Message, Attachment, FileAttachment } from './types'
import type { ModelCatalogEntry } from '@/types/models'

export interface ChatGridCardProps {
  chat: Chat
  models: ModelCatalogEntry[]
  onModelSelect: (model: Model) => void
  onUpdateMessages: (messages: Message[]) => void
  onRemove: () => void
  showRemove: boolean
  onToolExecuted?: (toolCallId: string, toolName: string, result: any) => void
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: any
  onFiltersChange?: (filters: any) => void
  providers?: string[]
  recentModelIds?: string[]
  conversationId: string
  // Per-chat options menu handlers
  onOpenInstructions?: () => void
  onCopyResponses?: () => void
  onCopyMetadata?: () => void
  onExportResponses?: () => void
  onExportMetadata?: () => void
  onSaveToKnowledgeBase?: () => void
  isSavingToKnowledgeBase?: boolean
  // Spark auto-fix support
  sendSparkFixRequest?: (content: string, sparkFixRequest: SparkFixRequest) => Promise<void>
  sparksEnabled?: boolean
}

export const ChatGridCard = memo(function ChatGridCard({
  chat,
  models,
  onModelSelect,
  onUpdateMessages,
  onRemove,
  showRemove,
  onToolExecuted,
  showFilters,
  onToggleFilters,
  hasActiveFilters,
  filters,
  onFiltersChange,
  providers,
  recentModelIds,
  conversationId,
  onOpenInstructions,
  onCopyResponses,
  onCopyMetadata,
  onExportResponses,
  onExportMetadata,
  onSaveToKnowledgeBase,
  isSavingToKnowledgeBase,
  sendSparkFixRequest,
  sparksEnabled,
}: ChatGridCardProps) {
  const { user } = useAuthStore()
  const { toast } = useToast()
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const hasMessages = chat.messages && chat.messages.length > 0

  // Image gallery state
  const [imageGalleryOpen, setImageGalleryOpen] = useState(false)
  const [galleryImages, setGalleryImages] = useState<{ src: string; alt: string }[]>([])
  const [gallerySelectedIndex, setGallerySelectedIndex] = useState(0)

  // PDF preview state
  const [isPdfOpen, setIsPdfOpen] = useState(false)
  const [pdfSrc, setPdfSrc] = useState('')
  const [pdfName, setPdfName] = useState('')

  // File preview state
  const [isFilePreviewOpen, setIsFilePreviewOpen] = useState(false)
  const [previewFile, setPreviewFile] = useState<{ name: string; size: number; content: string } | null>(null)

  const formatCost = useCallback((cost: number | null | undefined) => {
    if (cost === null || cost === undefined) return ''
    return pricingUtils.formatCost(cost)
  }, [])

  const formatLatency = useCallback(
    (latency: number | null | undefined) =>
      formatLatencyFromSeconds(latency ?? undefined, ''),
    []
  )

  // File preview handlers
  const handleOpenImageGallery = useCallback((images: { src: string; alt: string }[], selectedIndex: number) => {
    setGalleryImages(images)
    setGallerySelectedIndex(selectedIndex)
    setImageGalleryOpen(true)
  }, [])

  const handleOpenPdf = useCallback((src: string, name: string) => {
    setPdfSrc(src)
    setPdfName(name)
    setIsPdfOpen(true)
  }, [])

  const handleOpenTextFile = useCallback(async (file: FileAttachment) => {
    const fileName = file.file?.name || 'file'
    const fileSize = file.file?.size || 0

    // If we have textContent cached, show modal directly
    if (file.textContent) {
      setPreviewFile({ name: fileName, size: fileSize, content: file.textContent })
      setIsFilePreviewOpen(true)
      return
    }

    // If we have an assetId (after reload), fetch the content
    if (file.assetId) {
      try {
        const blob = await assetsAPI.download(file.assetId)
        if (blob) {
          const content = await blob.text()
          setPreviewFile({ name: fileName, size: fileSize, content })
          setIsFilePreviewOpen(true)
        } else {
          toast({ title: 'Error', description: 'Failed to load file content', variant: 'destructive' })
        }
      } catch (error) {
        console.error('Failed to fetch file content:', error)
        toast({ title: 'Error', description: 'Failed to load file content', variant: 'destructive' })
      }
      return
    }

    toast({ title: 'Error', description: 'File content not available', variant: 'destructive' })
  }, [toast])

  // Stub handlers - editing/retry not available in grid view
  const noop = useCallback(() => {}, [])
  const noopAsync = useCallback(async () => {}, [])

  const chatPanelContextValue = useMemo(() => ({
    model: chat.model,
    messages: chat.messages || [],
    isLoading: chat.isLoading,
    isGenerating: chat.isLoading,
    user,
    conversationId,
    chatId: chat.id,
    syncMode: false,
    messagesContainer: messagesContainerRef.current,
    cachedAttachments: {},
    disabledChat: false,
    onUpdateMessages,
    onToolExecuted,
    onRetry: noopAsync,
    onEditMessage: noopAsync,
    onCopyContent: noop,
    onCopyMetadata: noop,
    onExportContent: noop,
    onExportMetadata: noop,
    onOpenModelDetails: noop,
    formatCost,
    formatLatency,
    onOpenImageGallery: handleOpenImageGallery,
    onOpenPdf: handleOpenPdf,
    onOpenTextFile: handleOpenTextFile,
    onOpenAllAttachments: noop,
    onSpeak: noop,
    onStopSpeaking: noop,
    isSpeaking: false,
    isTTSLoading: false,
    isTTSSupported: false,
  }), [
    chat.model, chat.messages, chat.isLoading, chat.id, user, conversationId,
    onUpdateMessages, onToolExecuted, formatCost, formatLatency, noop, noopAsync,
    handleOpenImageGallery, handleOpenPdf, handleOpenTextFile
  ])

  return (
    <div className="flex flex-col bg-card rounded-xl border shadow-sm h-full overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-2 py-1.5 border-b bg-muted/20 flex-shrink-0">
        <div className="flex items-center gap-1 min-w-0 flex-1">
          <ModelComboBox
            models={models}
            value={chat.model?.model_id}
            onValueChange={(modelId) => {
              const model = models.find(m => m.model_id === modelId)
              if (model) onModelSelect(model as Model)
            }}
            showFilters={showFilters}
            onToggleFilters={onToggleFilters}
            hasActiveFilters={hasActiveFilters}
            filters={filters}
            onFiltersChange={onFiltersChange}
            providers={providers}
            recentModelIds={recentModelIds}
            variant="ghost"
          />
          {chat.isLoading && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground flex-shrink-0" />
          )}
        </div>

        <div className="flex items-center gap-0.5 flex-shrink-0">
          {/* Per-chat options menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-muted-foreground">
                <MoreVertical className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {onOpenInstructions && (
                <DropdownMenuItem onClick={onOpenInstructions}>
                  <ScrollText className="h-4 w-4 mr-2" /> Instructions
                </DropdownMenuItem>
              )}

              {(onCopyResponses || onExportResponses) && hasMessages && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuSub>
                    <DropdownMenuSubTrigger>
                      <FileText className="h-4 w-4 mr-2" /> Responses
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent>
                      {onCopyResponses && (
                        <DropdownMenuItem onClick={onCopyResponses}>
                          <Copy className="h-4 w-4 mr-2" /> Copy all
                        </DropdownMenuItem>
                      )}
                      {onExportResponses && (
                        <DropdownMenuItem onClick={onExportResponses}>
                          <Download className="h-4 w-4 mr-2" /> Export (.txt)
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                </>
              )}

              {(onCopyMetadata || onExportMetadata) && hasMessages && (
                <DropdownMenuSub>
                  <DropdownMenuSubTrigger>
                    <Braces className="h-4 w-4 mr-2" /> Metadata
                  </DropdownMenuSubTrigger>
                  <DropdownMenuSubContent>
                    {onCopyMetadata && (
                      <DropdownMenuItem onClick={onCopyMetadata}>
                        <Copy className="h-4 w-4 mr-2" /> Copy (JSON)
                      </DropdownMenuItem>
                    )}
                    {onExportMetadata && (
                      <DropdownMenuItem onClick={onExportMetadata}>
                        <Download className="h-4 w-4 mr-2" /> Export (.json)
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuSubContent>
                </DropdownMenuSub>
              )}

              {onSaveToKnowledgeBase && hasMessages && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={onSaveToKnowledgeBase}
                    disabled={isSavingToKnowledgeBase}
                  >
                    <BookOpen className="h-4 w-4 mr-2" />
                    Save to knowledge base
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          {showRemove && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRemove}
              className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </header>

      {/* Message area - full height */}
      <ChatPanelProvider value={chatPanelContextValue}>
        <div
          ref={messagesContainerRef}
          className="flex-1 overflow-y-auto"
        >
          {hasMessages ? (
            <div className="px-3 py-2">
              {sendSparkFixRequest ? (
                <SparkAutoFixProvider
                  sendSparkFixRequest={sendSparkFixRequest}
                  sparksEnabled={sparksEnabled}
                  isLoading={chat.isLoading}
                >
                  {/* MessageList reads messages/isLoading from ChatPanelContext */}
                  <MessageList />
                </SparkAutoFixProvider>
              ) : (
                <MessageList />
              )}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center p-3 text-center">
              {chat.model ? (
                <>
                  <ModelIcon
                    modelName={chat.model.name}
                    modelId={chat.model.model_id}
                    provider={chat.model.provider}
                    modelIconSlug={chat.model.model_icon_slug}
                    modelIconUrl={chat.model.model_icon_url}
                    providerIconSlug={chat.model.provider_icon_slug}
                    providerIconUrl={chat.model.provider_icon_url}
                    size={28}
                    showTooltip={false}
                    className="mb-2 opacity-40"
                  />
                  <p className="text-xs text-muted-foreground/70">
                    Ready
                  </p>
                </>
              ) : (
                <>
                  <MessageSquare className="h-7 w-7 mb-2 text-muted-foreground/20" />
                  <p className="text-xs text-muted-foreground/70">
                    Select model
                  </p>
                </>
              )}
            </div>
          )}
        </div>
      </ChatPanelProvider>

      {/* File Preview Modals */}
      {previewFile && (
        <FilePreviewModal
          isOpen={isFilePreviewOpen}
          onClose={() => setIsFilePreviewOpen(false)}
          fileName={previewFile.name}
          fileSize={previewFile.size}
          textContent={previewFile.content}
        />
      )}

      <PdfPreviewModal
        isOpen={isPdfOpen}
        onClose={() => setIsPdfOpen(false)}
        pdfSrc={pdfSrc}
        pdfName={pdfName}
      />

      <ImagePreviewModal
        isOpen={imageGalleryOpen}
        onClose={() => setImageGalleryOpen(false)}
        images={galleryImages}
        selectedIndex={gallerySelectedIndex}
        onIndexChange={setGallerySelectedIndex}
      />
    </div>
  )
})
