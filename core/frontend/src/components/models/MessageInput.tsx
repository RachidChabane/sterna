/**
 * MessageInput Component
 *
 * Unified input area for both Independent and Synced modes:
 * - Local state for performance (no parent re-renders on keystroke)
 * - Auto-resize textarea
 * - Attachment menu
 * - Drag & drop and paste support
 * - Optional: Global feature toggles (Synced mode)
 * - Optional: Cost estimation display
 * - Optional: Options menu (Independent mode)
 * - Fullscreen mode support
 */

import { memo, useState, useRef, useCallback, useEffect, useMemo } from 'react'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useSpeechToText, type AudioLevelEntry } from '@/hooks/useSpeechToText'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ImagePreviewModal } from './ImagePreviewModal'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { AutoResizeTextarea } from '@/components/ui/AutoResizeTextarea'
import { AttachmentMenu } from './AttachmentMenu'
import { GlobalFeatureToggles } from './GlobalFeatureToggles'
import { AttachmentPreviews } from './AttachmentPreviews'
import { MicrophoneButton } from './MicrophoneButton'
import {
  SendIcon,
  X,
  Calculator,
  Loader2Icon,
  MoreVertical,
  Trash2,
  Info,
  Square,
  Maximize2,
  Minimize2,
  Volume2,
  AudioLines,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useSettingsStore } from '@/store/settingsStore'
import { useNavigate } from '@tanstack/react-router'
import { useMentionAutocomplete } from '@/hooks/useMentionAutocomplete'
import { MentionAutocomplete } from './MentionAutocomplete'
import type { Model, Attachment } from './types'
import { isRecord, asNumber } from './tool-renderers/shared'
import type { MCPServer } from '@/api/mcp'

interface FeatureState {
  enabled: number
  total: number
  supported: number
}

interface MessageInputProps {
  // Mode
  mode: 'independent' | 'synced'

  // Input control
  disabled: boolean
  placeholder?: string
  externalValue?: string  // External value to fill the input (e.g., from suggestions)
  inputRef?: React.RefObject<HTMLTextAreaElement | null>

  // Model (for independent mode)
  model?: Model | null

  // Attachments
  attachments: Attachment[]
  onRemoveAttachment: (id: string) => void
  onAddAttachment: (attachment: Attachment) => void
  hasVisionSupport: boolean
  hasPDFSupport: boolean
  onFilterByCapability?: (modality: string) => void
  activeFilters?: string[]

  // Drag & drop
  isDropOver?: boolean
  onDragOver?: (e: React.DragEvent<HTMLDivElement>) => void
  onDragLeave?: (e: React.DragEvent<HTMLDivElement>) => void
  onDrop?: (e: React.DragEvent<HTMLDivElement>) => void | Promise<void>

  // Paste handler
  onPaste?: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void

  // Actions - onSend and onEstimate receive the input text
  onSend: (text: string) => void
  onCancel?: () => void
  canCancel?: boolean
  onEstimate?: (text: string) => void
  isEstimating?: boolean

  // Feature toggles (synced mode only)
  webSearchState?: FeatureState
  onToggleWebSearch?: () => void
  hasWebSearchSupport?: boolean
  reasoningState?: FeatureState
  onToggleReasoning?: () => void
  hasReasoningSupport?: boolean
  mcpToolsState?: FeatureState
  onToggleMCPTools?: () => void
  hasFunctionSupport?: boolean
  activeServers?: MCPServer[]
  fileToolsState?: FeatureState
  onToggleFileTools?: () => void
  imageGenerationState?: FeatureState
  onToggleImageGeneration?: () => void
  videoGenerationState?: FeatureState
  onToggleVideoGeneration?: () => void
  sparksState?: FeatureState
  onToggleSparks?: () => void
  knowledgeBaseState?: FeatureState
  onToggleKnowledgeBase?: () => void
  hasKnowledgeBaseSupport?: boolean

  // Cost estimation
  // Different callers feed this from different-shaped cost-estimate state
  // (a single-model estimate vs. a multi-model batch response); the display
  // below narrows the specific fields it reads rather than assuming one shape.
  estimatedCost?: unknown
  // Only ever called here to clear the estimate, so `null` (accepted by every
  // real setter's wider state type) is all this needs to require.
  setEstimatedCost?: (cost: null) => void

  // Independent mode options
  messages?: { role: string }[]
  isClearingChat?: boolean
  onShowClearDialog?: () => void
  hideHeaderActions?: boolean

  // Synced mode specific
  chats?: { model: Model | null; disabled?: boolean }[]
  chatsWithModels?: number

  // Floating mode (removes borders/shadows - container provides them)
  floatingMode?: boolean

  // Voice conversation mode - when active, uses external voice handlers
  voiceModeActive?: boolean
  voiceState?: 'idle' | 'listening' | 'processing' | 'speaking'
  onVoiceStartRecording?: () => Promise<boolean>
  onVoiceStopRecording?: () => Promise<string | null>
  onVoiceCancelRecording?: () => void
  voiceAudioLevels?: AudioLevelEntry[]
  // Handler to activate voice mode (shown as voice button when input is empty)
  onActivateVoice?: () => Promise<void>
}

// Memoized action buttons to prevent re-rendering on every keystroke
interface ActionButtonsProps {
  mode: 'independent' | 'synced'
  onEstimate?: () => void
  onCancel?: () => void
  onSend: () => void
  model?: Model | null
  hasInput: boolean
  hasAttachments: boolean
  isLoading: boolean
  loadingEstimate: boolean
  disabledChat: boolean
  estimatedCost: unknown
  canCancel: boolean
  chats?: { model: Model | null; disabled?: boolean }[]
  chatsWithModels?: number
  isFullscreen?: boolean
}

const ActionButtons = memo<ActionButtonsProps>(({
  mode,
  onEstimate,
  onCancel,
  onSend,
  model,
  hasInput,
  hasAttachments,
  isLoading,
  loadingEstimate,
  disabledChat,
  estimatedCost,
  canCancel,
  chats,
  chatsWithModels,
  isFullscreen = false,
}) => {
  // Calculate hasModels for synced mode
  const hasModels = useMemo(() => {
    if (mode === 'independent') {
      return !!model
    }
    return (chatsWithModels ?? chats?.filter(c => c.model !== null && !c.disabled).length ?? 0) > 0
  }, [mode, model, chats, chatsWithModels])

  const hasModelsSelected = useMemo(() => {
    if (mode === 'independent') return !!model
    return chats?.some(c => c.model !== null) ?? false
  }, [mode, model, chats])

  const allChatsDisabled = useMemo(() => {
    if (mode === 'independent') return false
    return hasModelsSelected && !hasModels
  }, [mode, hasModelsSelected, hasModels])

  // Memoize tooltip content
  const estimateTooltipText = useMemo(() => {
    if (loadingEstimate) return 'Estimating...'
    if (!hasModels) return mode === 'synced' ? 'Select at least one model' : 'Select a model first'
    if (!hasInput && !hasAttachments) return 'Enter a message or attach files'
    if (isLoading) return 'Please wait for response to complete'
    return 'Estimate Cost'
  }, [loadingEstimate, hasModels, hasInput, hasAttachments, isLoading, mode])

  const sendTooltipText = useMemo(() => {
    if (!hasModels) {
      return mode === 'synced' ? 'Select at least one model' : 'Select a model first'
    }
    if (isLoading || loadingEstimate) {
      return mode === 'synced' ? 'Please wait for responses to complete' : 'Please wait for response to complete'
    }
    if (allChatsDisabled) {
      return 'All chats are disabled. Please enable at least one chat.'
    }
    if (!hasInput && !hasAttachments) return 'Enter a message or attach files'
    return mode === 'synced' ? 'Send to All' : 'Send'
  }, [hasModels, isLoading, loadingEstimate, hasInput, hasAttachments, mode, allChatsDisabled])

  return (
    <div className="flex items-center gap-2">
      {onEstimate && !isFullscreen && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-block">
              <Button
                size="icon"
                variant="outline"
                onClick={onEstimate}
                disabled={!hasModels || (!hasInput && !hasAttachments) || isLoading || loadingEstimate || disabledChat}
                aria-label={estimateTooltipText}
                className={cn(
                  "h-9 w-9 rounded-full transition-all duration-400 ease-bounce hover:scale-110 hover:shadow-[0_0_20px_rgba(59,130,246,0.3)] hover:border-primary/50",
                  Boolean(estimatedCost) && "bg-accent-brand/10 border-accent-brand/30 hover:bg-accent-brand/20"
                )}
              >
                {loadingEstimate ? (
                  <Loader2Icon className="h-4 w-4 animate-spin" />
                ) : (
                  <Calculator className="h-4 w-4" />
                )}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{estimateTooltipText}</p>
          </TooltipContent>
        </Tooltip>
      )}
      {canCancel ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-block">
              <Button
                size="icon"
                variant="outline"
                onClick={onCancel}
                aria-label={mode === 'synced' ? 'Stop All' : 'Stop'}
                className={cn(
                  "h-9 w-9 rounded-full transition-all duration-400 ease-bounce hover:scale-110 hover:shadow-[0_0_20px_rgba(239,68,68,0.4)] hover:border-destructive/50",
                  mode === 'synced' && "bg-destructive/10 border border-destructive/30 hover:bg-destructive/20"
                )}
              >
                {mode === 'synced' ? (
                  <Square className="h-4 w-4 text-destructive" />
                ) : (
                  <X className="h-4 w-4" />
                )}
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{mode === 'synced' ? 'Stop All' : 'Stop'}</p>
          </TooltipContent>
        </Tooltip>
      ) : (
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-block">
              <Button
                size="icon"
                onClick={onSend}
                disabled={!hasModels || (!hasInput && !hasAttachments) || isLoading || loadingEstimate || disabledChat}
                aria-label={sendTooltipText}
                className="h-9 w-9 rounded-full transition-all duration-400 ease-bounce hover:scale-110 hover:shadow-[0_0_25px_rgba(59,130,246,0.5)] hover:brightness-110 disabled:opacity-50 disabled:hover:scale-100 disabled:hover:shadow-none"
              >
                <SendIcon className="h-4 w-4" />
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{sendTooltipText}</p>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
})

ActionButtons.displayName = 'ActionButtons'

function MessageInputComponent({
  mode,
  disabled,
  placeholder,
  externalValue,
  inputRef: externalInputRef,
  model,
  attachments,
  onRemoveAttachment,
  onAddAttachment,
  hasVisionSupport,
  hasPDFSupport,
  onFilterByCapability,
  activeFilters,
  isDropOver,
  onDragOver,
  onDragLeave,
  onDrop,
  onPaste,
  onSend,
  onCancel,
  canCancel = false,
  onEstimate,
  isEstimating = false,
  webSearchState,
  onToggleWebSearch,
  hasWebSearchSupport = false,
  reasoningState,
  onToggleReasoning,
  hasReasoningSupport = false,
  mcpToolsState,
  onToggleMCPTools,
  hasFunctionSupport = false,
  activeServers = [],
  fileToolsState,
  onToggleFileTools,
  imageGenerationState,
  onToggleImageGeneration,
  videoGenerationState,
  onToggleVideoGeneration,
  sparksState,
  onToggleSparks,
  knowledgeBaseState,
  onToggleKnowledgeBase,
  hasKnowledgeBaseSupport = false,
  estimatedCost,
  setEstimatedCost,
  messages = [],
  isClearingChat = false,
  onShowClearDialog,
  hideHeaderActions = false,
  chats,
  chatsWithModels,
  floatingMode = false,
  // Voice conversation mode props
  voiceModeActive = false,
  voiceState,
  onVoiceStartRecording,
  onVoiceStopRecording,
  onVoiceCancelRecording,
  voiceAudioLevels,
  onActivateVoice,
}: MessageInputProps) {
  // LOCAL state - isolated from parent for performance!
  const [localInput, setLocalInput] = useState('')
  const [cursorPos, setCursorPos] = useState(0)
  const [isFeaturePopoverOpen, setIsFeaturePopoverOpen] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [lineCount, setLineCount] = useState(1)
  const [previewImage, setPreviewImage] = useState<{ src: string; alt: string } | null>(null)
  const internalInputRef = useRef<HTMLTextAreaElement>(null)
  const lastExternalValueRef = useRef<string | undefined>(undefined)

  // Speech-to-text hook for MicrophoneButton (dictation only - inserts into textarea)
  // This is SEPARATE from voice conversation mode which auto-sends messages
  const {
    isRecording,
    isTranscribing,
    startRecording,
    stopRecording,
    cancelRecording,
    audioLevels,
  } = useSpeechToText()

  // Derive recording active state (for MicrophoneButton STT dictation)
  const isRecordingActive = isRecording || isTranscribing

  // Use external ref if provided, otherwise use internal
  const inputRef = externalInputRef || internalInputRef

  // Sync with external value (e.g., from suggested questions)
  useEffect(() => {
    if (externalValue !== undefined && externalValue !== lastExternalValueRef.current) {
      setLocalInput(externalValue)
      lastExternalValueRef.current = externalValue
    }
  }, [externalValue])

  // Get chat settings for enter-to-send behavior
  // On mobile, always use newline on Enter (better for touch keyboards)
  const isMobile = useMediaQuery('(max-width: 767px)')
  const enterToSendSetting = useSettingsStore((state) => state.chat.enterToSend)
  const enterToSend = isMobile ? false : enterToSendSetting

  // Navigation for clone-complete redirect
  const navigate = useNavigate()

  // Clone complete handler - navigates to the new conversation
  const handleCloneComplete = useCallback((conversationId: string) => {
    navigate({ to: '/chats', search: { conversation: conversationId } })
  }, [navigate])

  // Check if MCP tools are enabled for @mention autocomplete
  const mcpEnabled = hasFunctionSupport && (mcpToolsState?.enabled ?? 0) > 0

  // Mention autocomplete handler for inserting selected mention
  const handleMentionInsert = useCallback((newText: string, newCursorPos: number) => {
    setLocalInput(newText)
    setCursorPos(newCursorPos)
    // Set cursor position in the textarea after state update
    requestAnimationFrame(() => {
      if (inputRef.current) {
        inputRef.current.setSelectionRange(newCursorPos, newCursorPos)
        inputRef.current.focus()
      }
    })
  }, [inputRef])

  // Speech-to-text handlers
  const handleStartRecording = useCallback(async () => {
    await startRecording()
  }, [startRecording])

  const handleStopRecording = useCallback(async () => {
    const transcript = await stopRecording()
    if (transcript) {
      // Insert transcribed text into input
      setLocalInput(prev => {
        if (prev.length === 0) {
          return transcript
        }
        const needsSpace = prev.length > 0 && !prev.endsWith(' ') && !prev.endsWith('\n')
        return prev + (needsSpace ? ' ' : '') + transcript
      })
      // Focus the input after insertion
      requestAnimationFrame(() => {
        if (inputRef.current) {
          inputRef.current.focus()
          const len = inputRef.current.value.length
          inputRef.current.setSelectionRange(len, len)
        }
      })
    }
  }, [stopRecording, inputRef])

  const handleCancelRecording = useCallback(() => {
    cancelRecording()
  }, [cancelRecording])

  // @mention autocomplete hook
  const mention = useMentionAutocomplete(
    localInput,
    cursorPos,
    mcpEnabled,
    handleMentionInsert,
    handleCloneComplete
  )

  // Handlers
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Let mention autocomplete handle keyboard events first
    if (mention.handleKeyDown(e)) {
      return
    }
    // Enter to send: when enabled, Enter sends (Shift+Enter for newline)
    // When disabled, Enter adds newline (Ctrl/Cmd+Enter to send)
    const shouldSend = enterToSend
      ? e.key === 'Enter' && !e.shiftKey
      : e.key === 'Enter' && (e.ctrlKey || e.metaKey)

    if (shouldSend) {
      e.preventDefault()
      // Don't send if disabled (e.g., model is answering)
      if (disabled) return
      if (localInput.trim() || attachments.length > 0) {
        onSend(localInput)
        setLocalInput('')
      }
    }
    // Close fullscreen with Escape
    if (e.key === 'Escape' && isFullscreen) {
      e.preventDefault()
      setIsFullscreen(false)
    }
  }, [localInput, attachments, onSend, isFullscreen, disabled, enterToSend, isMobile, mention.handleKeyDown])

  const handleSendClick = useCallback(() => {
    // Don't send if disabled (e.g., model is answering)
    if (disabled) return
    if (localInput.trim() || attachments.length > 0) {
      onSend(localInput)
      setLocalInput('')
    }
  }, [localInput, attachments, onSend, disabled])

  const handleEstimateClick = useCallback(() => {
    if (onEstimate) {
      onEstimate(localInput)
    }
  }, [localInput, onEstimate])

  // Handle voice conversation button click - this is DIFFERENT from MicrophoneButton
  // Voice conversation: auto-sends message AND auto-reads AI response via TTS
  const handleVoiceButtonClick = useCallback(async () => {
    // If voice mode is not active, activate it (which also starts recording)
    if (!voiceModeActive && onActivateVoice) {
      await onActivateVoice()
      return
    }

    // Voice mode is active - handle based on current state
    if (voiceState === 'listening') {
      // Currently recording - stop recording (will auto-transcribe and auto-send via voice conversation hook)
      if (onVoiceStopRecording) {
        await onVoiceStopRecording()
      }
    } else if (voiceState === 'processing') {
      // Processing - do nothing, wait for transcription
      return
    } else {
      // Idle or speaking - start recording (will interrupt TTS if speaking)
      if (onVoiceStartRecording) {
        await onVoiceStartRecording()
      }
    }
  }, [voiceModeActive, onActivateVoice, voiceState, onVoiceStartRecording, onVoiceStopRecording])

  // Handle input changes - update both text and cursor position
  const handleInputChange = useCallback((value: string) => {
    setLocalInput(value)
    // Get cursor position after the change
    requestAnimationFrame(() => {
      if (inputRef.current) {
        setCursorPos(inputRef.current.selectionStart ?? 0)
      }
    })
  }, [inputRef])

  // Track cursor position on click and selection changes
  const handleCursorChange = useCallback(() => {
    if (inputRef.current) {
      setCursorPos(inputRef.current.selectionStart ?? 0)
    }
  }, [inputRef])

  // Memoize boolean flags to prevent ActionButtons re-render on every keystroke
  const hasInput = useMemo(() => localInput.length > 0, [localInput.length])
  const hasAttachments = useMemo(() => attachments.length > 0, [attachments.length])

  // Generate placeholder
  const finalPlaceholder = useMemo(() => {
    if (placeholder) return placeholder
    if (mode === 'synced') {
      return chats && chats.length > 1 ? 'Compare responses across models...' : 'Ask anything...'
    }
    return model ? 'Ask anything...' : 'Select a model first'
  }, [placeholder, mode, chats, model])

  // Show fullscreen button when there are 3+ lines
  const showFullscreenButton = lineCount >= 3

  return (
    <TooltipProvider>
      {/* Fullscreen backdrop - rendered via portal to escape container stacking contexts */}
      {isFullscreen && createPortal(
        <div
          className="fixed inset-0 z-40 bg-background/95 backdrop-blur-sm animate-in fade-in-0 duration-300"
          onClick={() => setIsFullscreen(false)}
        />,
        document.body
      )}

      <style>{`
        @keyframes borderGlow {
          0%, 100% {
            box-shadow: 0 0 0 0 rgba(59, 130, 246, 0);
          }
          50% {
            box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1);
          }
        }

        @keyframes gradientShift {
          0% {
            background-position: 0% 50%;
          }
          50% {
            background-position: 100% 50%;
          }
          100% {
            background-position: 0% 50%;
          }
        }

        .message-input-container {
          position: relative;
          transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
        }

        .message-input-container::before {
          content: '';
          position: absolute;
          inset: -1px;
          border-radius: inherit;
          padding: 1px;
          background: linear-gradient(135deg, transparent, transparent);
          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          -webkit-mask-composite: xor;
          mask-composite: exclude;
          opacity: 0;
          transition: opacity 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
          pointer-events: none; /* CRITICAL: Allow clicks through */
        }

        .message-input-container:focus-within,
        .message-input-container:hover,
        .message-input-container.popover-open {
          transform: translateY(-2px);
        }

        .message-input-container:focus-within::before,
        .message-input-container:hover::before,
        .message-input-container.popover-open::before {
          opacity: 1;
          background: linear-gradient(135deg,
            rgba(59, 130, 246, 0.5),
            rgba(61, 92, 228, 0.5),
            rgba(59, 130, 246, 0.5)
          );
          background-size: 200% 200%;
          animation: gradientShift 3s ease infinite;
        }

        .message-input-container.drag-over {
          animation: borderGlow 1.5s ease-in-out infinite;
        }

        .message-input-container.drag-over::before {
          opacity: 1;
          background: linear-gradient(135deg,
            rgba(59, 130, 246, 0.8),
            rgba(61, 92, 228, 0.8),
            rgba(59, 130, 246, 0.8)
          );
          background-size: 200% 200%;
          animation: gradientShift 1.5s ease infinite;
        }

        /* Light mode: better contrast with page background */
        .light .message-input-container {
          background: hsl(var(--card) / 0.95);
        }

        /* Fullscreen styles */
        .message-input-fullscreen {
          position: fixed !important;
          top: 50% !important;
          left: 50% !important;
          transform: translate(-50%, -50%) !important;
          width: calc(100% - 4rem) !important;
          max-width: 56rem !important;
          z-index: 50 !important;
          margin: 0 !important;
          padding: 1.5rem !important;
          animation: zoomIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }

        /* Mobile fullscreen adjustments */
        @media (max-width: 767px) {
          .message-input-fullscreen {
            width: calc(100% - 1.5rem) !important;
            padding: 1rem !important;
            top: auto !important;
            bottom: 1rem !important;
            transform: translateX(-50%) !important;
            max-height: 70vh;
            animation: slideUp 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
          }
        }

        @keyframes zoomIn {
          from {
            opacity: 0;
            transform: translate(-50%, -50%) scale(0.95);
          }
          to {
            opacity: 1;
            transform: translate(-50%, -50%) scale(1);
          }
        }

        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateX(-50%) translateY(1rem);
          }
          to {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
          }
        }

        /* Never apply hover transform when fullscreen */
        .message-input-fullscreen:focus-within,
        .message-input-fullscreen:hover {
          transform: translate(-50%, -50%) !important;
        }

        @media (max-width: 767px) {
          .message-input-fullscreen:focus-within,
          .message-input-fullscreen:hover {
            transform: translateX(-50%) !important;
          }
        }
      `}</style>
      {/* Input content - shared between fullscreen portal and normal render */}
      {(() => {
        const inputContent = (
          <>
            {isDropOver && (
              <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                <div className="px-3 py-1.5 text-xs rounded-md border-2 border-dashed border-primary/50 bg-background/80 backdrop-blur-sm text-primary">
                  Drop files or images to attach
                </div>
              </div>
            )}

            {/* Close fullscreen button */}
            {isFullscreen && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setIsFullscreen(false)}
                    className="absolute -top-2 -right-2 h-8 w-8 rounded-full z-10 bg-background border border-border hover:bg-accent"
                  >
                    <Minimize2 className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Exit fullscreen (Esc)</TooltipContent>
              </Tooltip>
            )}

            {/* Cost estimation display - only in Independent mode, hidden in fullscreen */}
            {mode === 'independent' && estimatedCost && !isFullscreen && (
              <div className="mb-2 space-y-1.5 px-3 py-2 bg-muted/50 border border-border/50 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-[11px]">
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <Calculator className="h-3 w-3" />
                      <span>Cost:</span>
                    </div>
                    <span className="font-mono font-semibold text-foreground">${asNumber(isRecord(estimatedCost) ? estimatedCost.cost : undefined)?.toFixed(4) || '0.0000'}</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEstimatedCost?.(null)}
                    className="h-4 w-4 p-0 hover:bg-muted"
                  >
                    <X className="h-2.5 w-2.5" />
                  </Button>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span>Prompt: <span className="font-mono font-semibold text-foreground">{asNumber(isRecord(estimatedCost) ? estimatedCost.prompt_tokens : undefined) || 0}</span></span>
                  <span>•</span>
                  <span>Completion: <span className="font-mono font-semibold text-foreground">{asNumber(isRecord(estimatedCost) ? estimatedCost.completion_tokens : undefined) || 0}</span></span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-0.5">
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0.5 h-4 border-muted-foreground/20 font-normal">
                    More accurate in English
                  </Badge>
                  {attachments.some((att) =>
                    att.type === 'image' || (att.type === 'file' && (
                      (att.file?.type === 'application/pdf') ||
                      ((att.file?.name || '').toLowerCase().endsWith('.pdf'))
                    ))
                  ) && (
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 h-4 border-muted-foreground/20 flex items-center gap-1">
                      <Info className="h-2.5 w-2.5" />
                      Images/PDFs not included
                    </Badge>
                  )}
                </div>
              </div>
            )}

            {/* Attachment Previews */}
            {attachments.length > 0 && (
              <AttachmentPreviews
                attachments={attachments}
                onRemove={onRemoveAttachment}
                onImageClick={(attachment) => {
                  if (attachment.type === 'image') {
                    setPreviewImage({ src: attachment.preview, alt: attachment.file.name })
                  }
                }}
              />
            )}

            <div className="flex flex-col gap-3 px-2 pt-1">
              {/* Main input area - shows either textarea or recording waveform */}
              {isRecordingActive ? (
                /* Recording active: full-width waveform replaces textarea */
                <div className="w-full min-h-[48px] py-2">
                  <MicrophoneButton
                    isRecording={isRecording}
                    isTranscribing={isTranscribing}
                    audioLevels={audioLevels}
                    onStartRecording={handleStartRecording}
                    onStopRecording={handleStopRecording}
                    onCancelRecording={handleCancelRecording}
                    disabled={disabled}
                    className="w-full"
                  />
                </div>
              ) : (
                /* Normal state: show textarea */
                <div className="relative">
                  <AutoResizeTextarea
                    ref={inputRef}
                    value={localInput}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    onKeyUp={handleCursorChange}
                    onClick={handleCursorChange}
                    onSelect={handleCursorChange}
                    onPaste={onPaste}
                    placeholder={finalPlaceholder}
                    className={cn(
                      "w-full border-0 focus:ring-0 bg-transparent text-foreground placeholder:text-muted-foreground",
                      isFullscreen && "text-base"
                    )}
                    disabled={disabled || (mode === 'independent' && !model)}
                    minHeight={isFullscreen ? 400 : 48}
                    maxHeight={isFullscreen ? 600 : 200}
                    onLineCountChange={setLineCount}
                  />

                  {/* @mention autocomplete dropdown */}
                  <MentionAutocomplete
                    isOpen={mention.isOpen}
                    mode={mention.mode}
                    items={mention.items}
                    activeIndex={mention.activeIndex}
                    selectedServer={mention.selectedServer}
                    inputRef={inputRef}
                    triggerStart={mention.triggerStart}
                    isLoadingSecondary={mention.isLoadingSecondary}
                    secondaryPickerTool={mention.secondaryPickerTool}
                    isCloningRepo={mention.isCloningRepo}
                    cloningRepoName={mention.cloningRepoName}
                    mediaConfig={mention.mediaConfig}
                    onMediaConfigChange={mention.updateMediaConfig}
                    onMediaConfigConfirm={mention.confirmMediaConfig}
                    onSelect={mention.selectItem}
                    onClose={mention.close}
                  />

                  {/* Fullscreen button - appears when 3+ lines and not in fullscreen */}
                  {showFullscreenButton && !isFullscreen && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setIsFullscreen(true)}
                          className={cn(
                            "absolute top-1 right-1 h-7 w-7 rounded-md",
                            "opacity-60 group-hover:opacity-100 hover:bg-accent hover:text-accent-foreground",
                            "focus:opacity-100 transition-opacity duration-200"
                          )}
                        >
                          <Maximize2 className="h-3.5 w-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>Expand fullscreen</TooltipContent>
                    </Tooltip>
                  )}
                </div>
              )}
              {/* Bottom row: action buttons (hidden when recording since waveform is in input area) */}
              {!isRecordingActive && (
                <div className="flex items-center justify-between gap-1 md:gap-2">
                  <div className="flex items-center gap-1 md:gap-2 min-w-0 flex-shrink">
                    {/* Options Menu - Only visible in independent mode when hideHeaderActions is true */}
                    {mode === 'independent' && hideHeaderActions && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={messages.length === 0}
                            title="Chat options"
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                          {onShowClearDialog && (
                            <DropdownMenuItem
                              onClick={onShowClearDialog}
                              disabled={messages.length === 0 || disabled || isClearingChat}
                            >
                              <Trash2 className="h-4 w-4 mr-2 text-destructive" />
                              Clear conversation
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}

                    {/* Attachment Menu */}
                    <AttachmentMenu
                      attachments={attachments}
                      onAttach={onAddAttachment}
                      onRemove={onRemoveAttachment}
                      disabled={disabled}
                    />

                    {/* Global Feature Toggles - Synced mode and floating mode (immersive) */}
                    {/* Note: Feature toggles should always be clickable (not disabled when no model selected) */}
                    {/* Users should be able to configure features before selecting a model */}
                    {(mode === 'synced' || floatingMode) && webSearchState && reasoningState && mcpToolsState && fileToolsState && imageGenerationState && videoGenerationState && sparksState && knowledgeBaseState && (
                      <GlobalFeatureToggles
                        webSearchState={webSearchState}
                        onToggleWebSearch={onToggleWebSearch!}
                        hasWebSearchSupport={hasWebSearchSupport}
                        reasoningState={reasoningState}
                        onToggleReasoning={onToggleReasoning!}
                        hasReasoningSupport={hasReasoningSupport}
                        mcpToolsState={mcpToolsState}
                        onToggleMCPTools={onToggleMCPTools!}
                        hasFunctionSupport={hasFunctionSupport}
                        activeServers={activeServers}
                        fileToolsState={fileToolsState}
                        onToggleFileTools={onToggleFileTools!}
                        imageGenerationState={imageGenerationState}
                        onToggleImageGeneration={onToggleImageGeneration!}
                        videoGenerationState={videoGenerationState}
                        onToggleVideoGeneration={onToggleVideoGeneration!}
                        sparksState={sparksState}
                        onToggleSparks={onToggleSparks!}
                        knowledgeBaseState={knowledgeBaseState}
                        onToggleKnowledgeBase={onToggleKnowledgeBase!}
                        hasKnowledgeBaseSupport={hasKnowledgeBaseSupport}
                        disabled={false}
                        onOpenChange={setIsFeaturePopoverOpen}
                      />
                    )}
                  </div>

                  {/* Right side: Microphone (STT) + Voice Conversation + Action Buttons */}
                  <div className="flex items-center gap-1 md:gap-2 flex-shrink-0">
                    {/* Microphone Button for Speech-to-Text (dictation into input) */}
                    <MicrophoneButton
                      isRecording={isRecording}
                      isTranscribing={isTranscribing}
                      audioLevels={audioLevels}
                      onStartRecording={handleStartRecording}
                      onStopRecording={handleStopRecording}
                      onCancelRecording={handleCancelRecording}
                      disabled={disabled}
                    />

                    {/* Action Buttons */}
                    <ActionButtons
                      mode={mode}
                      onEstimate={onEstimate ? handleEstimateClick : undefined}
                      onCancel={onCancel}
                      onSend={handleSendClick}
                      model={model}
                      hasInput={hasInput}
                      hasAttachments={hasAttachments}
                      isLoading={disabled}
                      loadingEstimate={isEstimating}
                      disabledChat={disabled}
                      estimatedCost={estimatedCost}
                      canCancel={canCancel}
                      chats={chats}
                      chatsWithModels={chatsWithModels}
                      isFullscreen={isFullscreen}
                    />
                  </div>
                </div>
              )}
            </div>
          </>
        )

        // When fullscreen, render via portal to escape stacking contexts (e.g., backdrop-blur on parent)
        if (isFullscreen) {
          return createPortal(
            <TooltipProvider>
              <div
                className="group relative message-input-container rounded-2xl border border-border bg-card p-4 shadow-sm message-input-fullscreen"
                onDragOver={onDragOver}
                onDragEnter={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
              >
                {inputContent}
              </div>
            </TooltipProvider>,
            document.body
          )
        }

        // Normal render
        return (
          <div className={cn(
            "flex-shrink-0",
            !floatingMode && mode === 'independent' && "mx-3 mb-4"
          )}>
            <div
              className={cn(
                "group relative",
                // Normal mode: full styling with hover effects
                !floatingMode && "message-input-container rounded-2xl border border-border bg-card p-4 shadow-sm",
                // Floating mode: minimal styling (container provides borders/shadow)
                floatingMode && "p-3",
                !floatingMode && mode === 'synced' && "mx-3 mb-4",
                !floatingMode && isDropOver && "drag-over",
                !floatingMode && isFeaturePopoverOpen && "popover-open"
              )}
              onDragOver={onDragOver}
              onDragEnter={onDragOver}
              onDragLeave={onDragLeave}
              onDrop={onDrop}
            >
              {inputContent}
            </div>
          </div>
        )
      })()}

      {/* Image Preview Modal */}
      <ImagePreviewModal
        isOpen={!!previewImage}
        onClose={() => setPreviewImage(null)}
        images={previewImage ? [previewImage] : []}
        selectedIndex={0}
        onIndexChange={() => {}}
      />
    </TooltipProvider>
  )
}

// Memoize to prevent unnecessary re-renders when parent updates
export const MessageInput = memo(MessageInputComponent)
