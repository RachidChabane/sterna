import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Copy, Download, RotateCw, Volume2, VolumeX, Loader2 } from 'lucide-react'
import type { Message } from './types'

interface MessageActionMenusProps {
  message: Message
  onCopyContent: () => void
  onCopyMetadata: () => void
  onExportContent: () => void
  onExportMetadata: () => void
  showRetry?: boolean
  onRetry?: () => void
  disabled?: boolean
  // TTS props
  onSpeak?: () => void
  onStopSpeaking?: () => void
  isSpeaking?: boolean
  isTTSLoading?: boolean
  isTTSSupported?: boolean
}

export function MessageActionMenus({
  message,
  onCopyContent,
  onCopyMetadata,
  onExportContent,
  onExportMetadata,
  showRetry = false,
  onRetry,
  disabled = false,
  onSpeak,
  onStopSpeaking,
  isSpeaking = false,
  isTTSLoading = false,
  isTTSSupported = true,
}: MessageActionMenusProps) {
  return (
    <TooltipProvider>
      {/* Copy dropdown */}
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6 hover:bg-accent group/btn" disabled={disabled}>
                <Copy className="h-3 w-3 text-muted-foreground group-hover/btn:text-accent-brand transition-colors" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="left">
            <p>Copy</p>
          </TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={onCopyContent}>
            Copy response
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onCopyMetadata}>
            Copy metadata (JSON)
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Export dropdown */}
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-6 w-6 hover:bg-accent group/btn" disabled={disabled}>
                <Download className="h-3 w-3 text-muted-foreground group-hover/btn:text-accent-brand transition-colors" />
              </Button>
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="left">
            <p>Export</p>
          </TooltipContent>
        </Tooltip>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onClick={onExportContent}>
            Export response (.txt)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={onExportMetadata}>
            Export metadata (.json)
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* TTS (Text-to-Speech) button */}
      {isTTSSupported && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 hover:bg-accent group/btn"
              onClick={() => (isSpeaking || isTTSLoading) ? onStopSpeaking?.() : onSpeak?.()}
              disabled={disabled}
            >
              {isTTSLoading ? (
                <Loader2 className="h-3 w-3 text-accent-brand animate-spin" />
              ) : isSpeaking ? (
                <VolumeX className="h-3 w-3 text-accent-brand transition-colors" />
              ) : (
                <Volume2 className="h-3 w-3 text-muted-foreground group-hover/btn:text-accent-brand transition-colors" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">
            <p>{isTTSLoading ? 'Loading...' : isSpeaking ? 'Stop reading' : 'Read aloud'}</p>
          </TooltipContent>
        </Tooltip>
      )}

      {/* Retry button (optional) */}
      {showRetry && onRetry && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 hover:bg-accent group/btn"
              onClick={onRetry}
              disabled={disabled}
            >
              <RotateCw className="h-3 w-3 text-muted-foreground group-hover/btn:text-accent-brand transition-colors" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">
            <p>Retry message</p>
          </TooltipContent>
        </Tooltip>
      )}
    </TooltipProvider>
  )
}

