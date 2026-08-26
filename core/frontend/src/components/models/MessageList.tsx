/**
 * MessageList Component
 *
 * Renders the list of chat messages with full functionality:
 * - User and assistant messages with avatars
 * - Reasoning display
 * - Tool call approval cards
 * - Attachments (images, PDFs, text files)
 * - Message actions (copy, export, retry)
 * - Web sources display
 */

import { useState, useRef, memo, useEffect, useCallback } from 'react'
import useEmblaCarousel from 'embla-carousel-react'
import { createPortal } from 'react-dom'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { CachedAvatar } from '@/components/ui/CachedAvatar'
import { Button } from '@/components/ui/button'
import { AutoResizeTextarea } from '@/components/ui/AutoResizeTextarea'
import { ImagePreviewModal } from './ImagePreviewModal'
import {
  UserIcon,
  BotIcon,
  KeyRound,
  RotateCw,
  Paperclip,
  FileText as FileTextIcon,
  Pencil,
  X,
  Check,
  Minimize2,
  SendIcon,
  ChevronLeft,
  ChevronRight,
  Play,
  Music,
  StopCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { useChatPanelContext, useChatPanelContextSafe } from './ChatPanelContext'
import { ModelIcon } from './ModelIcon'
import { useSettingsStore } from '@/store/settingsStore'
import { ReasoningDisplay } from './ReasoningDisplay'
import { ToolCallApprovalCard } from '@/components/mcp'
import { Markdown } from '@/components/ui/markdown'
import { MessageActionMenus } from './MessageActionMenus'
import { MessageDetailsTooltip } from './MessageDetailsTooltip'
import { WebSourcesDisplay } from './WebSourcesDisplay'
import { FileToolExecutionsDisplay } from './FileToolExecutionsDisplay'
import { MessageSteps } from './MessageSteps'
import { MentionText } from './MentionText'
import { AssetImage } from './AssetImage'
import { getApiErrorMessage } from '@/utils/errorMessages'
import { assetsAPI } from '@/api/assets'
import { mcpApi, type MCPToolApproval, type MCPToolExecution } from '@/api/mcp'
import { extractTextFromContent, stripActionTags } from '@/utils/chatUtils'
import { useStreamingText } from '@/hooks/useStreamingText'
import { getFileExtension } from '@/utils/fileUtils'
import { TypeBadge } from '@/lib/type-badges'
import { formatFileSize } from '@/utils/imageUtils'
import type { Attachment, ImageAttachment, FileAttachment, VideoAttachment, AudioAttachment, AttachmentLike, WebSource } from './types'

// Helper to format timestamp - always shows date and time in user-friendly format
function formatTimestamp(date: Date): string {
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const isYesterday = new Date(now.getTime() - 86400000).toDateString() === date.toDateString()
  const isThisYear = date.getFullYear() === now.getFullYear()

  const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

  if (isToday) return `Today at ${timeStr}`
  if (isYesterday) return `Yesterday at ${timeStr}`

  // For dates within this year, show "Mon, Jan 15 at 2:30 PM"
  if (isThisYear) {
    const dateStr = date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
    return `${dateStr} at ${timeStr}`
  }

  // For older dates, include year: "Mon, Jan 15, 2023 at 2:30 PM"
  const dateStr = date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
  return `${dateStr} at ${timeStr}`
}

// Wrapper that applies smooth streaming text reveal to Markdown content
function StreamingMarkdown({ content, isStreaming, className, webSources }: {
  content: string
  isStreaming: boolean
  className?: string
  webSources?: WebSource[]
}) {
  const ctx = useChatPanelContextSafe()
  const { displayedText, isRevealing } = useStreamingText(
    content,
    isStreaming,
    ctx?.stopRevealRef
  )

  // Notify parent when reveal state changes
  const prevRevealingRef = useRef(false)
  useEffect(() => {
    if (isRevealing !== prevRevealingRef.current) {
      prevRevealingRef.current = isRevealing
      ctx?.onTextRevealChange?.(isRevealing)
    }
  }, [isRevealing])

  return (
    <Markdown webSources={webSources} className={className}>
      {displayedText}
    </Markdown>
  )
}

// Message attachments carousel component - clean, refined design
interface MessageAttachmentsCarouselProps {
  attachments: Attachment[]
  cachedAttachments: Record<string, { base64?: string; name?: string; textContent?: string; size?: number }>
  onOpenImageGallery: (images: { src: string; alt: string; assetId?: string }[], startIndex: number, isGenerated: boolean) => void
  onOpenPdf: (source: string, name: string) => void
  onOpenTextFile: (file: FileAttachment) => void
}

function MessageAttachmentsCarousel({
  attachments,
  cachedAttachments,
  onOpenImageGallery,
  onOpenPdf,
  onOpenTextFile,
}: MessageAttachmentsCarouselProps) {
  const imgAtts = attachments.filter(a => a.type === 'image') as ImageAttachment[]
  const docAtts = attachments.filter(a => a.type === 'file') as FileAttachment[]
  const videoAtts = attachments.filter(a => a.type === 'video') as VideoAttachment[]
  const audioAtts = attachments.filter(a => a.type === 'audio') as AudioAttachment[]
  const allItems = [...imgAtts, ...videoAtts, ...audioAtts, ...docAtts]
  // Use carousel when items would overflow ~340px viewport (2 cards visible)
  const useCarousel = allItems.length >= 3

  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: false,
    align: 'start',
    slidesToScroll: 1,
    containScroll: 'trimSnaps',
  })

  const [canScrollPrev, setCanScrollPrev] = useState(false)
  const [canScrollNext, setCanScrollNext] = useState(false)

  const scrollPrev = useCallback(() => emblaApi?.scrollPrev(), [emblaApi])
  const scrollNext = useCallback(() => emblaApi?.scrollNext(), [emblaApi])

  const onSelect = useCallback(() => {
    if (!emblaApi) return
    setCanScrollPrev(emblaApi.canScrollPrev())
    setCanScrollNext(emblaApi.canScrollNext())
  }, [emblaApi])

  useEffect(() => {
    if (!emblaApi || !useCarousel) return
    onSelect()
    emblaApi.on('select', onSelect)
    emblaApi.on('reInit', onSelect)
    return () => {
      emblaApi.off('select', onSelect)
      emblaApi.off('reInit', onSelect)
    }
  }, [emblaApi, onSelect, useCarousel])

  // Render an image attachment card - clean with subtle shadow
  const renderImageCard = (img: ImageAttachment, idx: number) => {
    const cached = cachedAttachments[img.id]
    const fileName = img.file?.name || cached?.name || 'image'
    const assetId = img.assetId || img.id
    return (
      <button
        key={`img-${img.id}`}
        type="button"
        onClick={() => {
          const images = imgAtts.map((i, imgIdx) => {
            const c = cachedAttachments[i.id]
            const assetId = i.assetId || i.id
            // Prefer base64 for immediate display, fallback to asset download URL
            const src = i.base64 || c?.base64 || (assetId ? `/api/workspaces/assets/${assetId}/download/` : '')
            return {
              src,
              alt: i.file?.name || c?.name || `Image ${imgIdx + 1}`,
              assetId
            }
          })
          onOpenImageGallery(images, idx, false)
        }}
        className="group relative flex-shrink-0 w-[140px] h-[88px] rounded-lg overflow-hidden bg-muted/50 ring-1 ring-border/50 hover:ring-primary/50 active:ring-primary/70 active:scale-[0.98] transition-all duration-200 shadow-sm hover:shadow-md touch-manipulation"
      >
        <AssetImage
          assetId={assetId}
          base64={img.base64}
          cachedBase64={cached?.base64}
          alt={fileName}
          className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-[1.02] group-active:scale-100"
        />
        {/* Subtle gradient overlay on hover/active */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 group-active:opacity-100 transition-opacity pointer-events-none" />
      </button>
    )
  }

  // Render a document attachment card - elegant with badge in corner
  const renderDocCard = (f: FileAttachment) => {
    const cached = cachedAttachments[f.id]
    const name = f.file?.name || cached?.name || 'file'
    const extension = getFileExtension(name)
    const assetId = f.assetId || f.id
    const hasBase64 = !!(f.base64 || cached?.base64)
    const hasTextContent = !!(f.textContent || cached?.textContent)
    // PDF detection: extension matters, not whether text was extracted
    // PDFs may have extracted textContent for AI but should still open in PDF viewer
    const isPdf = extension.toLowerCase() === 'pdf' && (hasBase64 || !!assetId)
    const fileSize = f.file?.size || cached?.size || 0

    return (
      <button
        key={`doc-${f.id}`}
        type="button"
        onClick={async () => {
          if (isPdf) {
            let pdfSource = f.base64 || cached?.base64
            if (!pdfSource && assetId) {
              const blob = await assetsAPI.download(assetId)
              if (blob) pdfSource = URL.createObjectURL(blob)
            }
            if (pdfSource) onOpenPdf(pdfSource, name)
          } else if (f.textContent || cached?.textContent) {
            onOpenTextFile({
              id: f.id, type: 'file', file: f.file || ({} as File),
              base64: undefined, textContent: f.textContent || cached?.textContent,
            })
          } else if (assetId) {
            onOpenTextFile({
              id: f.id, type: 'file',
              file: f.file || { name, type: (f as AttachmentLike).fileType || 'text/plain', size: fileSize } as File,
              base64: undefined, textContent: undefined, assetId,
            })
          }
        }}
        className="group relative flex-shrink-0 w-[140px] h-[88px] rounded-lg bg-muted/30 ring-1 ring-border/50 hover:ring-primary/50 hover:bg-muted/50 active:ring-primary/70 active:bg-muted/60 active:scale-[0.98] transition-all duration-200 shadow-sm hover:shadow-md p-2.5 flex flex-col touch-manipulation"
        title={name}
      >
        {/* Extension badge - top left corner */}
        <TypeBadge type={extension} className="absolute top-2 left-2" />

        {/* File info - bottom aligned */}
        <div className="mt-auto pt-5">
          <p className="text-[11px] font-medium truncate text-left leading-tight text-foreground/90">
            {name}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5 text-left">
            {formatFileSize(fileSize)}
          </p>
        </div>
      </button>
    )
  }

  // Render a video attachment card
  const renderVideoCard = (v: VideoAttachment) => {
    const name = v.file?.name || (v as AttachmentLike).fileName || 'video'
    const assetId = v.assetId || v.id
    const previewUrl = v.preview || (assetId ? `/api/workspaces/assets/${assetId}/download/` : '')
    return (
      <div
        key={`vid-${v.id}`}
        className="group relative flex-shrink-0 w-[160px] h-[88px] rounded-lg overflow-hidden bg-muted/50 ring-1 ring-border/50 transition-all duration-200 shadow-sm"
        title={name}
      >
        <video
          src={previewUrl}
          preload="metadata"
          className="w-full h-full object-cover"
          muted
        />
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none">
          <div className="h-7 w-7 rounded-full bg-black/60 flex items-center justify-center">
            <Play className="h-3.5 w-3.5 text-white ml-0.5" fill="white" />
          </div>
        </div>
        <TypeBadge type={getFileExtension(name)} className="absolute bottom-1.5 left-1.5" />
      </div>
    )
  }

  // Render an audio attachment card
  const renderAudioCard = (a: AudioAttachment) => {
    const name = a.file?.name || (a as AttachmentLike).fileName || 'audio'
    const fileSize = a.file?.size || (a as AttachmentLike).fileSize || 0
    return (
      <div
        key={`aud-${a.id}`}
        className="group relative flex-shrink-0 w-[140px] h-[88px] rounded-lg overflow-hidden ring-1 ring-border/50 transition-all duration-200 shadow-sm p-2.5 flex flex-col bg-gradient-to-br from-purple-500/20 to-pink-500/20"
        title={name}
      >
        <div className="flex items-center gap-1.5">
          <Music className="h-4 w-4 text-purple-400 flex-shrink-0" />
          <TypeBadge type={getFileExtension(name)} />
        </div>
        <div className="mt-auto">
          <p className="text-[11px] font-medium truncate text-left leading-tight text-foreground/90">
            {name}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5 text-left">
            {formatFileSize(fileSize)}
          </p>
        </div>
      </div>
    )
  }

  // Simple flex layout for < 3 items
  if (!useCarousel) {
    return (
      <div className="mb-2 flex justify-end">
        <div className="flex items-center gap-2">
          {imgAtts.map((img, idx) => renderImageCard(img, idx))}
          {videoAtts.map((v) => renderVideoCard(v))}
          {audioAtts.map((a) => renderAudioCard(a))}
          {docAtts.map((f) => renderDocCard(f))}
        </div>
      </div>
    )
  }

  // Carousel layout for >= 3 items - constrained width to force scrolling
  return (
    <div className="mb-2 flex justify-end">
      <div className="relative w-[340px]">
        {/* Carousel viewport */}
        <div className="overflow-hidden rounded-lg" ref={emblaRef}>
          <div className="flex gap-2">
            {imgAtts.map((img, idx) => renderImageCard(img, idx))}
            {videoAtts.map((v) => renderVideoCard(v))}
            {audioAtts.map((a) => renderAudioCard(a))}
            {docAtts.map((f) => renderDocCard(f))}
          </div>
        </div>

        {/* Fade overlays */}
        {canScrollPrev && (
          <div className="absolute left-0 top-0 bottom-0 w-10 bg-gradient-to-r from-background via-background/80 to-transparent pointer-events-none z-[5] rounded-l-lg" />
        )}
        {canScrollNext && (
          <div className="absolute right-0 top-0 bottom-0 w-10 bg-gradient-to-l from-background via-background/80 to-transparent pointer-events-none z-[5] rounded-r-lg" />
        )}

        {/* Navigation buttons - larger touch targets on mobile */}
        {canScrollPrev && (
          <Button
            variant="ghost"
            size="sm"
            onClick={scrollPrev}
            className="absolute -left-3 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full bg-background hover:bg-muted active:bg-muted/80 active:scale-95 border border-border shadow-md hover:shadow-lg transition-all touch-manipulation"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        )}
        {canScrollNext && (
          <Button
            variant="ghost"
            size="sm"
            onClick={scrollNext}
            className="absolute -right-3 top-1/2 -translate-y-1/2 h-8 w-8 p-0 z-10 rounded-full bg-background hover:bg-muted active:bg-muted/80 active:scale-95 border border-border shadow-md hover:shadow-lg transition-all touch-manipulation"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  )
}

export function MessageList() {
  const {
    messages,
    model,
    user,
    isLoading,
    isGenerating,
    messagesContainer,
    cachedAttachments,
    conversationId,
    chatId,
    disabledChat,
    onUpdateMessages,
    onToolExecuted,
    onRetry,
    onEditMessage,
    onCopyContent,
    onCopyMetadata,
    onExportContent,
    onExportMetadata,
    onOpenModelDetails,
    formatCost,
    formatLatency,
    onOpenImageGallery,
    onOpenPdf,
    onOpenTextFile,
    onOpenAllAttachments,
    onSpeak,
    onStopSpeaking,
    isSpeaking,
    isTTSLoading,
    isTTSSupported,
  } = useChatPanelContext()
  const { toast } = useToast()

  // Get chat display settings
  const chatSettings = useSettingsStore((state) => state.chat)
  const { compactMode, showTimestamps, showModelName, showModelIcon, showUserAvatar } = chatSettings

  // Mobile detection for fullscreen edit
  const isMobile = useMediaQuery('(max-width: 767px)')

  // Inline editing state
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null)
  const [editingContent, setEditingContent] = useState<string>('')

  // Image preview state
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null)

  // Track visual viewport height for keyboard adaptation
  const [viewportHeight, setViewportHeight] = useState<number | null>(null)

  // Listen to visual viewport changes (keyboard open/close)
  useEffect(() => {
    if (!isMobile || editingMessageIndex === null) return

    const viewport = window.visualViewport
    if (!viewport) return

    const updateHeight = () => {
      setViewportHeight(viewport.height)
    }

    // Set initial height
    updateHeight()

    viewport.addEventListener('resize', updateHeight)
    viewport.addEventListener('scroll', updateHeight)

    return () => {
      viewport.removeEventListener('resize', updateHeight)
      viewport.removeEventListener('scroll', updateHeight)
    }
  }, [isMobile, editingMessageIndex])

  // Handle closing fullscreen edit
  const handleCloseEdit = () => {
    setEditingMessageIndex(null)
    setEditingContent('')
    setViewportHeight(null)
  }

  // Handle sending edited message
  const handleSendEdit = () => {
    if (editingMessageIndex !== null && editingContent.trim()) {
      onEditMessage(editingMessageIndex, editingContent)
      setEditingMessageIndex(null)
      setEditingContent('')
      setViewportHeight(null)
    }
  }

  return (
    <>
    <div className={cn("space-y-4 py-4", compactMode && "space-y-2 py-2")}>
      {(() => {
        const filteredMessages = messages
          .filter(message => message.role !== 'tool')
          .filter(message => !(message.isError && !message.content))
        // Find the index of the last assistant message for streaming indicator
        let lastAssistantIdx = -1
        for (let i = filteredMessages.length - 1; i >= 0; i--) {
          if (filteredMessages[i].role === 'assistant') { lastAssistantIdx = i; break }
        }
        return filteredMessages.map((message, index) => {
        // Detect streaming per-message: the last assistant message without cost/tokens is still being generated.
        // We don't rely solely on isGenerating because it checks the raw (unfiltered) last message,
        // which can be a tool message mid-stream, causing isGenerating to be false during active streaming.
        const isStreamingMessage = index === lastAssistantIdx &&
          message.role === 'assistant' &&
          !message.cost &&
          !message.tokens &&
          !message.isError &&
          !message.isUnsupported &&
          !message.is_stopped
        return (
        <div
          key={`${message.role}-${message.timestamp.getTime()}-${index}`}
          data-message-role={message.role}
          className={cn(
            "flex gap-2 md:gap-3 animate-message-in group",
            message.role === 'user' && "flex-row-reverse",
            compactMode && "gap-2"
          )}
          style={{
            animationDelay: `${index * 0.05}s`
          }}
        >
          {/* Avatar - hidden on mobile, respects showUserAvatar/showModelIcon settings on desktop */}
          {message.role === 'user' ? (
            <CachedAvatar
              src={user?.avatar_url}
              alt={`${user?.first_name || ''} ${user?.last_name || ''}`}
              className={cn(
                "h-8 w-8 bg-muted flex-shrink-0",
                "hidden", // Always hidden on mobile
                showUserAvatar && "md:flex" // Only show on desktop if setting enabled
              )}
              fallbackClassName="bg-muted text-muted-foreground"
              fallback={<UserIcon className="h-4 w-4" />}
            />
          ) : (
            <div className={cn(
              "w-8 h-8 items-center justify-center flex-shrink-0 relative",
              "hidden", // Always hidden on mobile
              showModelIcon && "md:flex" // Only show on desktop if setting enabled
            )}>
              {(() => {
                // Check if message has content (show icon even on error if there's content)
                const hasContent = typeof message.content === 'string'
                  ? message.content.trim().length > 0
                  : Array.isArray(message.content) && message.content.length > 0
                const showIcon = !message.isError || hasContent

                if (message.model && message.model_id && message.provider && showIcon && showModelName) {
                  return (
                    <button
                      type="button"
                      className={cn(
                        "p-0 m-0 inline-flex items-center justify-center rounded hover:opacity-90 focus:outline-none",
                        isStreamingMessage && "streaming-icon-breathe"
                      )}
                      onClick={() => onOpenModelDetails(message.model_id)}
                      title={message.model}
                    >
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
                    </button>
                  )
                } else if (showIcon) {
                  return <BotIcon className={cn("h-8 w-8", isStreamingMessage && "streaming-icon-breathe")} />
                }
                return null
              })()}
              {/* Sterna "via Model" badge */}
              {message.sterna_route && (
                <span className="text-[10px] text-muted-foreground/60 leading-none mt-1 truncate max-w-[80px]" title={`Routed by Sterna (score: ${message.sterna_route.score})`}>
                  via {message.sterna_route.resolved_model_name}
                </span>
              )}
            </div>
          )}

          {/* Message Content */}
          <div
            className={cn(
              "space-y-1 break-words relative min-w-0",
              message.role === 'user'
                ? editingMessageIndex === index && !isMobile
                  ? "text-right flex-1" // Full width when editing on desktop
                  : "text-right max-w-[75%] md:max-w-[60%]"
                : "flex-1"
            )}
          >
            {/* Tool call approval requests */}
            {message.role === 'assistant' && message.pending_approvals && message.pending_approvals.length > 0 && (
              <div className="space-y-2 mt-2">
                {message.pending_approvals.map((approval) => (
                  <ToolCallApprovalCard
                    key={approval.id}
                    approval={approval}
                    onApprove={async (approvalId: string, scope: 'once' | 'session' | 'permanent') => {
                      try {
                        // Call the API to approve the tool
                        const response = await mcpApi.approve(approvalId, scope)
                        // The approve endpoint actually returns { status, message, approval,
                        // execution } (see core/mcp/views.py approve action), but api/mcp.ts
                        // declares only MCPToolApproval. Access the extra field explicitly.
                        const { execution } = response.data as MCPToolApproval & {
                          execution?: MCPToolExecution
                        }

                        // Remove this approval from the message's pending_approvals
                        if (onUpdateMessages) {
                          const updatedMessages = messages.map(msg => {
                            if (msg.timestamp === message.timestamp) {
                              return {
                                ...msg,
                                pending_approvals: msg.pending_approvals?.filter((a) => a.id !== approvalId)
                              }
                            }
                            return msg
                          })
                          onUpdateMessages(updatedMessages)
                        }

                        // Find the tool_call_id for this approval
                        const toolCall = message.tool_calls?.find(
                          tc => tc.function.name === approval.tool_name
                        )

                        // Notify parent to continue conversation with tool result
                        if (onToolExecuted && toolCall && execution) {
                          onToolExecuted(toolCall.id, approval.tool_name, execution.result)
                        }

                        // Show success toast
                        toast({
                          title: 'Tool approved',
                          description: `${approval.tool_name} has been approved and executed successfully.`,
                        })
                      } catch (error) {
                        console.error('Failed to approve tool:', error)
                        toast({
                          title: 'Approval failed',
                          description: getApiErrorMessage(error, 'Failed to approve tool execution'),
                          variant: 'destructive',
                        })
                      }
                    }}
                    onReject={async (approvalId: string) => {
                      try {
                        // Call the API to reject the tool
                        await mcpApi.reject(approvalId)

                        // Remove this approval from the message's pending_approvals
                        if (onUpdateMessages) {
                          const updatedMessages = messages.map(msg => {
                            if (msg.timestamp === message.timestamp) {
                              return {
                                ...msg,
                                pending_approvals: msg.pending_approvals?.filter((a) => a.id !== approvalId)
                              }
                            }
                            return msg
                          })
                          onUpdateMessages(updatedMessages)
                        }

                        // Show success toast
                        toast({
                          title: 'Tool rejected',
                          description: `${approval.tool_name} has been rejected and will not execute.`,
                        })
                      } catch (error) {
                        console.error('Failed to reject tool:', error)
                        toast({
                          title: 'Rejection failed',
                          description: getApiErrorMessage(error, 'Failed to reject tool execution'),
                          variant: 'destructive',
                        })
                      }
                    }}
                  />
                ))}
              </div>
            )}

            {/* Steps-based display for multi-step tool execution flow */}
            {message.role === 'assistant' && message.steps && message.steps.length > 0 ? (
              <div className="w-full max-w-full min-w-0" style={{ overflow: 'hidden' }}>
                <MessageSteps
                  steps={message.steps}
                  isInterrupted={message.isInterrupted}
                  isStreaming={isStreamingMessage}
                  chatId={chatId}
                  conversationId={conversationId}
                  model={model}
                  messages={messages}
                />
              </div>
            ) : (
              <>
                {/* Reasoning display for assistant messages (legacy path) */}
                {message.role === 'assistant' && (message.reasoning_content || message.is_reasoning) && (
                  <div className={cn("block w-full mb-2", !message.is_reasoning && "mt-2")}>
                    <ReasoningDisplay
                      content={message.is_reasoning ? extractTextFromContent(message.content) : (message.reasoning_content || '')}
                      isStreaming={Boolean(message.is_reasoning)}
                      isInterrupted={message.isInterrupted}
                    />
                  </div>
                )}

                {/* File tool executions display - show before message content (legacy) */}
                {message.role === 'assistant' && message.file_tool_executions && message.file_tool_executions.length > 0 && (
                  <FileToolExecutionsDisplay executions={message.file_tool_executions} />
                )}

                {/* Attachments rendering ABOVE user message - carousel when > 3 items */}
                {message.role === 'user' && message.attachments && message.attachments.length > 0 && (
                  <MessageAttachmentsCarousel
                    attachments={message.attachments as Attachment[]}
                    cachedAttachments={cachedAttachments}
                    onOpenImageGallery={onOpenImageGallery}
                    onOpenPdf={onOpenPdf}
                    onOpenTextFile={onOpenTextFile}
                  />
                )}

                {/* Only show regular message bubble if NOT currently in reasoning phase AND has actual text content */}
                {/* Attachments are rendered separately above via MessageAttachmentsCarousel */}
                {!message.is_reasoning && message.content && extractTextFromContent(message.content).trim() && (
                  <>
                    {/* Inline editing mode for user messages (desktop only - mobile uses fullscreen) */}
                    {message.role === 'user' && editingMessageIndex === index && !isMobile ? (
                      <div className="w-full">
                        <AutoResizeTextarea
                          value={editingContent}
                          onChange={setEditingContent}
                          className="w-full text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground"
                          minHeight={80}
                          maxHeight={300}
                          autoFocus
                        />
                        <div className="flex justify-end gap-2 mt-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleCloseEdit}
                            className="h-8 px-3 text-xs"
                          >
                            <X className="h-3.5 w-3.5 mr-1" />
                            Cancel
                          </Button>
                          <Button
                            variant="default"
                            size="sm"
                            onClick={handleSendEdit}
                            disabled={!editingContent.trim()}
                            className="h-8 px-3 text-xs"
                          >
                            <Check className="h-3.5 w-3.5 mr-1" />
                            Send
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div
                        className={cn(
                          "inline-block text-base break-words max-w-full",
                          message.role === 'user'
                            ? "px-4 py-2.5 rounded-2xl bg-primary/15 text-foreground rounded-tr-sm border border-primary/20"
                            : message.isError
                            ? "px-4 py-2.5 rounded-2xl bg-destructive/10 text-red-400 border border-destructive/20"
                            : message.isUnsupported
                            ? "text-muted-foreground"
                            : "text-foreground"
                        )}
                      >
                        {/* User messages with @mentions use MentionText for styled rendering */}
                        {message.role === 'user' && extractTextFromContent(message.content).includes('@') ? (
                          <MentionText className="text-base">
                            {extractTextFromContent(message.content)}
                          </MentionText>
                        ) : message.role === 'assistant' ? (
                          <StreamingMarkdown
                            content={stripActionTags(extractTextFromContent(message.content))}
                            isStreaming={isStreamingMessage}
                            webSources={message.web_sources}
                            className={cn(
                              "[&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
                              !message.isUnsupported && cn(
                                message.isError && "prose-p:text-red-400 prose-strong:text-red-300 prose-headings:text-red-300 prose-li:text-red-400 prose-code:text-red-400/80",
                                !message.isError && "prose-p:text-foreground prose-strong:text-foreground prose-headings:text-foreground prose-li:text-foreground prose-code:text-primary prose-a:text-primary prose-a:no-underline hover:prose-a:underline"
                              )
                            )}
                          />
                        ) : (
                          <Markdown
                            className={cn(
                              "[&>*:first-child]:mt-0 [&>*:last-child]:mb-0",
                              "prose-p:text-foreground prose-strong:text-foreground prose-headings:text-foreground prose-li:text-foreground prose-code:text-primary prose-a:text-primary prose-a:no-underline hover:prose-a:underline"
                            )}
                          >
                            {extractTextFromContent(message.content)}
                          </Markdown>
                        )}

                        {/* Generated images from image generation models */}
                        {message.role === 'assistant' && message.images && message.images.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {message.images.map((imgSrc, imgIndex) => (
                              <button
                                key={imgIndex}
                                type="button"
                                onClick={() => {
                                  const images = message.images!.map((src, i) => ({
                                    src,
                                    alt: `Generated image ${i + 1}`
                                  }))
                                  onOpenImageGallery(images, imgIndex, false)
                                }}
                                className="block rounded-lg overflow-hidden border border-border/50 hover:border-accent-brand/50 transition-colors cursor-zoom-in"
                              >
                                <img
                                  src={imgSrc}
                                  alt={`Generated image ${imgIndex + 1}`}
                                  className="max-w-[400px] max-h-[400px] object-contain bg-background/50"
                                  loading="lazy"
                                />
                              </button>
                            ))}
                          </div>
                        )}

                        {/* Direct-resolution actions for key-related errors */}
                        {message.role === 'assistant' && message.isError &&
                        (message.errorCode === 'no_api_key' ||
                          message.errorCode === 'invalid_api_key' ||
                          message.errorCode === 'insufficient_credits') && (
                          <div className="mt-3 flex flex-wrap items-center gap-2">
                            <Button
                              variant="default"
                              size="sm"
                              onClick={() => useSettingsStore.getState().openSettings('apikey')}
                            >
                              <KeyRound className="h-3.5 w-3.5 mr-1.5" />
                              {message.errorCode === 'no_api_key' ? 'Add an API key' : 'Check API key settings'}
                            </Button>
                            {message.errorCode === 'no_api_key' && (
                              <span className="text-xs text-muted-foreground">
                                Your key stays yours — requests are billed by your provider, not by us.
                              </span>
                            )}
                          </div>
                        )}

                        {/* Retry button for error messages (only last assistant message) */}
                        {message.role === 'assistant' && message.isError && onUpdateMessages && !disabledChat &&
                        index === messages.findLastIndex(m => m.role === 'assistant') && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onRetry(index)}
                            disabled={isLoading}
                            className="mt-3 border-destructive/50 text-destructive hover:bg-destructive/10 hover:text-destructive hover:border-destructive"
                          >
                            <RotateCw className="h-3.5 w-3.5 mr-1.5" />
                            Retry
                          </Button>
                        )}
                      </div>
                    )}
                  </>
                )}

                {/* Standalone generated images display (when no text content) */}
                {message.role === 'assistant' && !message.content && message.images && message.images.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {message.images.map((imgSrc, imgIndex) => (
                      <button
                        key={imgIndex}
                        type="button"
                        onClick={() => {
                          const images = message.images!.map((src, i) => ({
                            src,
                            alt: `Generated image ${i + 1}`
                          }))
                          onOpenImageGallery(images, imgIndex, false)
                        }}
                        className="block rounded-lg overflow-hidden border border-border/50 hover:border-accent-brand/50 transition-colors cursor-zoom-in"
                      >
                        <img
                          src={imgSrc}
                          alt={`Generated image ${imgIndex + 1}`}
                          className="max-w-[400px] max-h-[400px] object-contain bg-background/50"
                          loading="lazy"
                        />
                      </button>
                    ))}
                  </div>
                )}

              </>
            )}

            {/* Message actions and timestamp for user messages */}
            {message.role === 'user' && !disabledChat && editingMessageIndex !== index && (
              <div className="flex justify-end mt-2 text-xs items-center gap-2">
                {showTimestamps && (
                  <span className="text-muted-foreground/60 text-[10px]">
                    {formatTimestamp(message.timestamp)}
                  </span>
                )}
                {/* Edit button - only show if message has text content */}
                {extractTextFromContent(message.content).trim() && (
                  <div className="flex items-center gap-1 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        setEditingMessageIndex(index)
                        setEditingContent(extractTextFromContent(message.content))
                      }}
                      disabled={isGenerating}
                      className="h-6 w-6 hover:bg-accent group/btn"
                    >
                      <Pencil className="h-3 w-3 text-muted-foreground group-hover/btn:text-accent-brand transition-colors" />
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* Timestamp for user messages when editing is disabled */}
            {message.role === 'user' && (disabledChat || editingMessageIndex === index) && showTimestamps && (
              <div className="flex justify-end mt-1 text-xs">
                <span className="text-muted-foreground/60 text-[10px]">
                  {formatTimestamp(message.timestamp)}
                </span>
              </div>
            )}

            {/* Response stopped indicator */}
            {message.role === 'assistant' && message.is_stopped && (
              <div className="flex items-center gap-2 mt-1.5 text-xs text-muted-foreground/70">
                <StopCircle className="h-3 w-3" />
                <span>Response stopped</span>
                {onUpdateMessages && !disabledChat &&
                 index === messages.findLastIndex(m => m.role === 'assistant') && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-5 px-1.5 text-xs text-muted-foreground/70 hover:text-foreground"
                    onClick={() => onRetry(index)}
                  >
                    Resend
                  </Button>
                )}
              </div>
            )}

            {/* Message actions for assistant messages */}
            {message.role === 'assistant' && !message.isError && !message.isUnsupported && (
              <div className="flex flex-wrap items-center gap-2 mt-2 text-xs">
                {showTimestamps && (
                  <span className="text-muted-foreground/60 text-[10px]">
                    {formatTimestamp(message.timestamp)}
                  </span>
                )}
                <div className="flex items-center gap-1 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                  <MessageDetailsTooltip
                    message={message}
                    messagesContainer={messagesContainer}
                    formatCost={formatCost}
                    formatLatency={formatLatency}
                    disabled={isLoading}
                  />
                  <MessageActionMenus
                    message={message}
                    onCopyContent={() => onCopyContent(message.content)}
                    onCopyMetadata={() => onCopyMetadata(message)}
                    onExportContent={() => onExportContent(message.content, message.model)}
                    onExportMetadata={() => onExportMetadata(message)}
                    showRetry={Boolean(
                      onUpdateMessages &&
                      !disabledChat &&
                      index === messages.findLastIndex(m => m.role === 'assistant') &&
                      (message.cost !== undefined || message.tokens !== undefined || message.isError || message.isInterrupted)
                    )}
                    onRetry={onUpdateMessages ? () => onRetry(index) : undefined}
                    disabled={isLoading}
                    onSpeak={onSpeak ? () => onSpeak(extractTextFromContent(message.content)) : undefined}
                    onStopSpeaking={onStopSpeaking}
                    isSpeaking={isSpeaking ?? false}
                    isTTSLoading={isTTSLoading ?? false}
                    isTTSSupported={isTTSSupported ?? true}
                  />
                </div>
              </div>
            )}

            {/* Web search sources - positioned at bottom right of assistant message */}
            {message.role === 'assistant' && message.web_sources && message.web_sources.length > 0 && (
              <div className="absolute bottom-0 right-0">
                <WebSourcesDisplay sources={message.web_sources} />
              </div>
            )}
          </div>
        </div>
      )})})()}
    </div>

    {/* Mobile Fullscreen Edit Portal */}
    {isMobile && editingMessageIndex !== null && createPortal(
      <>
        {/* Backdrop */}
        <div
          className="fixed inset-0 z-40 bg-background/95 backdrop-blur-sm animate-in fade-in-0 duration-300"
          onClick={handleCloseEdit}
        />
        {/* Fullscreen Edit Container */}
        <div
          className="fixed left-0 right-0 top-0 z-50 flex flex-col"
          style={{
            height: viewportHeight ? `${viewportHeight}px` : '100dvh',
            paddingTop: 'max(env(safe-area-inset-top, 0px), 1rem)',
            paddingBottom: '1rem',
            paddingLeft: 'max(env(safe-area-inset-left, 0px), 1rem)',
            paddingRight: 'max(env(safe-area-inset-right, 0px), 1rem)',
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-2 pb-4">
            <h2 className="text-lg font-semibold">Edit Message</h2>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleCloseEdit}
              className="h-9 w-9 rounded-full"
            >
              <X className="h-5 w-5" />
            </Button>
          </div>

          {/* Input Container with embedded footer */}
          <div className="flex-1 flex flex-col mx-2 border border-border rounded-xl bg-card overflow-hidden">
            {/* Textarea area */}
            <div className="flex-1 overflow-auto">
              <AutoResizeTextarea
                value={editingContent}
                onChange={setEditingContent}
                className="w-full h-full text-base border-0 px-4 py-3 bg-transparent focus:ring-0"
                minHeight={100}
                maxHeight={(viewportHeight || window.innerHeight) - 180}
                autoFocus
              />
            </div>

            {/* Footer Actions - inside the input container */}
            <div className="flex items-center justify-end gap-2 px-3 py-3 border-t border-border bg-muted/30">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCloseEdit}
                className="h-9 px-4"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSendEdit}
                disabled={!editingContent.trim()}
                className="h-9 px-4"
              >
                <SendIcon className="h-4 w-4 mr-2" />
                Send
              </Button>
            </div>
          </div>
        </div>
      </>,
      document.body
    )}

    {/* Image Preview Modal */}
    <ImagePreviewModal
      isOpen={!!previewImage}
      onClose={() => setPreviewImage(null)}
      images={previewImage ? [previewImage] : []}
      selectedIndex={0}
      onIndexChange={() => {}}
    />
    </>
  )
}
