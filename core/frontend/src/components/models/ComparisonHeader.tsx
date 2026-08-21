/**
 * ComparisonHeader Component
 *
 * Header section for ModelComparisonPage with:
 * - Title and description
 * - Token count warning badge
 * - Conversations button
 * - Consigliere button
 * - Clear button
 * - Copy/Export dropdown
 */

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
import {
  MessageSquare,
  Copy,
  Sparkles,
  AlertTriangle,
  Plus,
  MoreVertical,
  FileDown,
  Trash2,
} from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { useNavigate } from '@tanstack/react-router'
import type { Model, ChatGroup } from './types'

interface ComparisonHeaderProps {
  // Token warning
  totalTokens: number
  highTokenThreshold: number

  // Conversations
  conversationsModalOpen: boolean
  onToggleConversations: () => void

  // Consigliere
  activeGroup: ChatGroup | undefined
  currentModel: Model | null
  hasMessages: boolean
  onOpenConsigliere: () => void

  // Clear
  onShowClearDialog: () => void

  // Copy/Export
  onCopyResponses: () => void
  onCopyMetadata: () => void
  onExportResponses: () => void
  onExportMetadata: () => void
}

export function ComparisonHeader({
  totalTokens,
  highTokenThreshold,
  conversationsModalOpen,
  onToggleConversations,
  activeGroup,
  currentModel,
  hasMessages,
  onOpenConsigliere,
  onShowClearDialog,
  onCopyResponses,
  onCopyMetadata,
  onExportResponses,
  onExportMetadata,
}: ComparisonHeaderProps) {
  const navigate = useNavigate()

  const handleNewConversation = () => {
    navigate({ to: '/chats', search: { new: true } })
  }

  return (
    <div className="px-6 py-3 flex-shrink-0 bg-background">
      <div className="flex justify-between items-center">
        {/* Left: Title + Token Badge */}
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold">Chats</h1>
          {totalTokens > highTokenThreshold && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-700 dark:text-amber-400 text-xs font-medium">
                    <AlertTriangle className="h-3 w-3" />
                    <span>{Math.round(totalTokens / 1000)}k</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-sm max-w-xs">
                    <p className="font-medium">High Token Count</p>
                    <p className="text-muted-foreground mt-1">
                      Performance may be affected. Try hiding/clearing chats or create a new conversation.
                    </p>
                  </div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>

        {/* Right: Action Buttons */}
        <div className="flex items-center gap-1.5">
          {/* Conversation Actions */}
          <div className="flex items-center gap-1">
            {/* All Conversations */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onToggleConversations}
                    className={cn(
                      "h-8 w-8 p-0",
                      conversationsModalOpen && "bg-secondary"
                    )}
                  >
                    <MessageSquare className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>All Conversations</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* New Conversation */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleNewConversation}
                    className="h-8 w-8 p-0"
                  >
                    <Plus className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>New Conversation</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {/* Actions Menu */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                >
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                {/* Clear */}
                <DropdownMenuItem onClick={onShowClearDialog}>
                  <Trash2 className="h-4 w-4 mr-2 text-destructive" />
                  Clear Conversation
                </DropdownMenuItem>

                {/* Separator */}
                <Separator className="my-1" />

                {/* Copy Section */}
                <DropdownMenuItem onClick={onCopyResponses} disabled={!hasMessages}>
                  <Copy className="h-4 w-4 mr-2" />
                  Copy Responses
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onCopyMetadata} disabled={!hasMessages}>
                  <Copy className="h-4 w-4 mr-2" />
                  Copy Metadata
                </DropdownMenuItem>

                {/* Separator */}
                <Separator className="my-1" />

                {/* Export Section */}
                <DropdownMenuItem onClick={onExportResponses} disabled={!hasMessages}>
                  <FileDown className="h-4 w-4 mr-2" />
                  Export Responses
                </DropdownMenuItem>
                <DropdownMenuItem onClick={onExportMetadata} disabled={!hasMessages}>
                  <FileDown className="h-4 w-4 mr-2" />
                  Export Metadata
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <Separator orientation="vertical" className="h-6" />

          {/* Consigliere */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-block">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onOpenConsigliere}
                    disabled={!activeGroup || !currentModel || !hasMessages}
                    className="gap-1.5"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Consigliere
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <p>
                  {!hasMessages
                    ? "Start a conversation to get AI recommendations"
                    : "Get AI-powered model recommendations"}
                </p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>
    </div>
  )
}
