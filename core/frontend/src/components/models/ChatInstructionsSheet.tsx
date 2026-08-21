/**
 * ChatInstructionsSheet Component
 *
 * A sheet/panel for editing chat-specific custom instructions.
 * - Desktop: Right-side panel with proper width
 * - Mobile: Bottom sheet covering most of the screen
 */

import { useState, useEffect } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  ToggleGroup,
  ToggleGroupItem,
} from '@/components/ui/toggle-group'
import { ScrollText, Info, ChevronDown } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { useSettingsStore } from '@/store/settingsStore'
import { useUIStore } from '@/store/uiStore'
import { validateInstructions, getWarning, MAX_INSTRUCTIONS_LENGTH } from '@/lib/promptProtection'
import type { ChatInstructions, ChatInstructionsMode } from './types'

interface ChatInstructionsSheetProps {
  isOpen: boolean
  onClose: () => void
  instructions?: ChatInstructions
  onSave: (instructions: ChatInstructions | undefined) => void
  /** Optional model name to display which chat's instructions are being edited (for grid view) */
  modelName?: string
}

export function ChatInstructionsSheet({
  isOpen,
  onClose,
  instructions,
  onSave,
  modelName,
}: ChatInstructionsSheetProps) {
  const isMobile = useUIStore((state) => state.isMobile)
  const { instructions: globalInstructions } = useSettingsStore()

  // Local state for editing
  const [enabled, setEnabled] = useState(!!instructions?.content)
  const [content, setContent] = useState(instructions?.content || '')
  const [mode, setMode] = useState<ChatInstructionsMode>(instructions?.mode || 'append')
  const [showGlobalPreview, setShowGlobalPreview] = useState(false)
  const [validationError, setValidationError] = useState<string | null>(null)

  // Validate content on change
  const handleContentChange = (newContent: string) => {
    setContent(newContent)
    const result = validateInstructions(newContent)
    setValidationError(result.isValid ? null : result.error || null)
  }

  // Reset state when sheet opens
  useEffect(() => {
    if (isOpen) {
      setEnabled(!!instructions?.content)
      setContent(instructions?.content || '')
      setMode(instructions?.mode || 'append')
      setShowGlobalPreview(false)
      setValidationError(null)
    }
  }, [isOpen, instructions])

  const handleSave = () => {
    // Validate before saving
    const result = validateInstructions(content)
    if (!result.isValid) {
      setValidationError(result.error || 'Invalid instructions')
      return
    }

    if (enabled && content.trim()) {
      onSave({
        content: content.trim(),
        mode,
      })
    } else {
      // Clear instructions if disabled or empty
      onSave(undefined)
    }
    onClose()
  }

  const warning = getWarning(content)

  const hasGlobalInstructions = globalInstructions.enabled && globalInstructions.content.trim()

  // Shared content component
  const InstructionsContent = ({ isMobileLayout = false }: { isMobileLayout?: boolean }) => (
    <div className={cn(
      "flex flex-col",
      isMobileLayout ? "flex-1 min-h-0" : "flex-1"
    )}>
      {/* Scrollable content area */}
      <div className={cn(
        "flex-1 overflow-y-auto",
        isMobileLayout ? "px-4 pb-4" : "px-6 py-4"
      )}>
        <div className="space-y-5">
          {/* Enable toggle */}
          <div className={cn(
            "flex items-center justify-between rounded-lg border border-border p-4",
            enabled ? "bg-primary/5 border-primary/20" : "bg-muted/30"
          )}>
            <div className="space-y-0.5 pr-4">
              <Label
                htmlFor="chat-instructions-enabled"
                className={cn(
                  "font-medium cursor-pointer",
                  isMobileLayout ? "text-base" : "text-sm"
                )}
              >
                Enable Chat Instructions
              </Label>
              <p className={cn(
                "text-muted-foreground",
                isMobileLayout ? "text-sm" : "text-xs"
              )}>
                Add custom instructions for this chat
              </p>
            </div>
            <Switch
              id="chat-instructions-enabled"
              checked={enabled}
              onCheckedChange={setEnabled}
              className="flex-shrink-0"
            />
          </div>

          {/* Mode selector - only show if global instructions exist and enabled */}
          {hasGlobalInstructions && enabled && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Label className={cn(
                  "font-medium",
                  isMobileLayout ? "text-base" : "text-sm"
                )}>
                  Combine with global
                </Label>
                {!isMobileLayout && (
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Info className="h-4 w-4 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent side="top" className="max-w-xs">
                        <p className="text-xs">
                          <strong>Append:</strong> Chat instructions added after global.
                          <br /><br />
                          <strong>Override:</strong> Only chat instructions used.
                        </p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                )}
              </div>
              <ToggleGroup
                type="single"
                value={mode}
                onValueChange={(value) => value && setMode(value as ChatInstructionsMode)}
                className="justify-start w-full"
              >
                <ToggleGroupItem
                  value="append"
                  className={cn(
                    "flex-1",
                    isMobileLayout ? "h-11 text-sm" : "h-9 text-xs"
                  )}
                >
                  Append to global
                </ToggleGroupItem>
                <ToggleGroupItem
                  value="override"
                  className={cn(
                    "flex-1",
                    isMobileLayout ? "h-11 text-sm" : "h-9 text-xs"
                  )}
                >
                  Override global
                </ToggleGroupItem>
              </ToggleGroup>
              {isMobileLayout && (
                <p className="text-xs text-muted-foreground">
                  {mode === 'append'
                    ? 'Your chat instructions will be added after your global instructions.'
                    : 'Only your chat instructions will be used, ignoring global instructions.'}
                </p>
              )}
            </div>
          )}

          {/* Global instructions preview (collapsible) */}
          {hasGlobalInstructions && enabled && (
            <Collapsible open={showGlobalPreview} onOpenChange={setShowGlobalPreview}>
              <CollapsibleTrigger asChild>
                <button className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors w-full">
                  <ChevronDown className={cn(
                    "h-4 w-4 transition-transform",
                    showGlobalPreview && "rotate-180"
                  )} />
                  <span>View global instructions</span>
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2">
                <div className="rounded-lg border border-border bg-muted/30 p-3 max-h-32 overflow-y-auto">
                  <p className={cn(
                    "text-muted-foreground whitespace-pre-wrap",
                    isMobileLayout ? "text-sm" : "text-xs"
                  )}>
                    {globalInstructions.content}
                  </p>
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}

          {/* Instructions content */}
          <div className="space-y-2">
            <Label
              htmlFor="chat-instructions-content"
              className={cn(
                "font-medium",
                isMobileLayout ? "text-base" : "text-sm"
              )}
            >
              Your Instructions
            </Label>
            <textarea
              id="chat-instructions-content"
              value={content}
              onChange={(e) => handleContentChange(e.target.value)}
              placeholder={`Enter instructions for this chat...

Example:
- Focus on Python code examples
- Keep responses under 500 words
- Use a formal tone`}
              disabled={!enabled}
              maxLength={MAX_INSTRUCTIONS_LENGTH}
              className={cn(
                "w-full rounded-lg border bg-background text-foreground",
                "placeholder:text-muted-foreground/50 resize-none",
                "focus:outline-none focus:ring-2 focus:ring-offset-2",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                validationError
                  ? "border-destructive focus:ring-destructive"
                  : "border-border focus:ring-ring",
                isMobileLayout
                  ? "min-h-[180px] p-4 text-base"
                  : "min-h-[160px] p-3 text-sm"
              )}
            />
            {/* Validation error */}
            {validationError && enabled && (
              <p className={cn(
                "text-destructive font-medium",
                isMobileLayout ? "text-sm" : "text-xs"
              )}>
                {validationError}
              </p>
            )}
            {/* Character count warning */}
            {warning && enabled && !validationError && (
              <p className={cn(
                "text-amber-500",
                isMobileLayout ? "text-sm" : "text-xs"
              )}>
                {warning}
              </p>
            )}
            {!hasGlobalInstructions && enabled && !validationError && !warning && (
              <p className={cn(
                "text-muted-foreground",
                isMobileLayout ? "text-sm" : "text-xs"
              )}>
                These instructions will be sent with every message in this chat.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Fixed footer with buttons */}
      <div className={cn(
        "flex-shrink-0 border-t border-border bg-background",
        isMobileLayout ? "p-4 pb-6" : "px-6 py-4"
      )}>
        <div className={cn(
          "flex gap-3",
          isMobileLayout ? "flex-col-reverse" : "justify-end"
        )}>
          <Button
            variant="outline"
            onClick={onClose}
            className={cn(isMobileLayout && "h-12")}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!!validationError}
            className={cn(isMobileLayout && "h-12")}
          >
            Save Instructions
          </Button>
        </div>
      </div>
    </div>
  )

  // Mobile: Bottom sheet
  if (isMobile) {
    return (
      <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <SheetContent
          side="bottom"
          className="h-[85vh] rounded-t-2xl p-0 flex flex-col"
        >
          {/* Drag handle indicator */}
          <div className="flex justify-center pt-3 pb-2 flex-shrink-0">
            <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
          </div>

          <SheetHeader className="flex-shrink-0 px-4 pb-4 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <ScrollText className="h-5 w-5 text-primary" />
              </div>
              <div className="text-left">
                <SheetTitle className="text-lg">
                  Chat Instructions
                </SheetTitle>
                <SheetDescription className="text-sm">
                  {modelName ? `Instructions for ${modelName}` : 'Custom instructions for this chat'}
                </SheetDescription>
              </div>
            </div>
          </SheetHeader>
          <InstructionsContent isMobileLayout={true} />
        </SheetContent>
      </Sheet>
    )
  }

  // Desktop: Right panel
  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="w-[480px] max-w-[90vw] p-0 flex flex-col"
      >
        <SheetHeader className="flex-shrink-0 px-6 pt-6 pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
              <ScrollText className="h-4 w-4 text-primary" />
            </div>
            <div className="text-left">
              <SheetTitle>
                Chat Instructions
              </SheetTitle>
              <SheetDescription>
                {modelName ? `Instructions for ${modelName}` : 'Custom instructions for this chat'}
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>
        <InstructionsContent isMobileLayout={false} />
      </SheetContent>
    </Sheet>
  )
}
