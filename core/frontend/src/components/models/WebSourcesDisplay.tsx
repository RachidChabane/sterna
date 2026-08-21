/**
 * WebSourcesDisplay Component
 *
 * Displays web search sources/citations from OpenRouter web search
 * Shows up to 3 favicon icons that are clickable, with a "Sources" button
 * that opens a modal (desktop) or bottom sheet (mobile)
 */

import React, { useState } from 'react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  TooltipPortal,
} from '@/components/ui/tooltip'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/store/uiStore'
import type { WebSource } from './types'

interface WebSourcesDisplayProps {
  sources: WebSource[]
}

export const WebSourcesDisplay: React.FC<WebSourcesDisplayProps> = ({ sources }) => {
  const [isOpen, setIsOpen] = useState(false)
  const isMobile = useUIStore((state) => state.isMobile)

  if (!sources || sources.length === 0) {
    return null
  }

  const getFaviconUrl = (url: string) => {
    try {
      const domain = new URL(url).hostname
      return `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
    } catch {
      return null
    }
  }

  const getHostname = (url: string) => {
    try {
      return new URL(url).hostname.replace(/^www\./, '')
    } catch {
      return url
    }
  }

  const getDomainName = (url: string) => {
    const hostname = getHostname(url)
    const domainParts = hostname.split('.')
    return domainParts.length > 1 ? domainParts[0] : hostname
  }

  // Only show first 3 sources in preview
  const previewSources = sources.slice(0, 3)

  // Shared sources list content
  const SourcesList = (
    <div className="space-y-1">
      {sources.map((source, index) => {
        const faviconUrl = getFaviconUrl(source.url)
        const hostname = getHostname(source.url)
        const domainName = getDomainName(source.url)

        return (
          <a
            key={index}
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(
              "group flex items-start gap-3 p-3 rounded-lg",
              "hover:bg-muted/50 active:bg-muted/70 transition-colors"
            )}
          >
            {/* Favicon */}
            <div className="flex-shrink-0 h-9 w-9 rounded-md bg-muted/50 border border-border flex items-center justify-center overflow-hidden">
              {faviconUrl ? (
                <img
                  src={faviconUrl}
                  alt={hostname}
                  className="h-5 w-5"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none'
                  }}
                />
              ) : (
                <span className="text-sm font-medium text-muted-foreground">
                  {hostname.charAt(0).toUpperCase()}
                </span>
              )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-foreground line-clamp-2 leading-snug group-hover:text-accent-brand transition-colors">
                {source.title || domainName}
              </div>
              <div className="text-xs text-muted-foreground mt-1 truncate">
                {hostname}
              </div>
            </div>

            {/* External link */}
            <div className="flex-shrink-0 self-center opacity-0 group-hover:opacity-100 transition-opacity">
              <ExternalLink className="h-4 w-4 text-muted-foreground" />
            </div>
          </a>
        )
      })}
    </div>
  )

  return (
    <>
      <div className="mt-2 flex items-center gap-2">
        {/* Stacked favicon icons (max 3) */}
        <div className="flex items-center">
          {previewSources.map((source, index) => {
            const faviconUrl = getFaviconUrl(source.url)
            const hostname = getHostname(source.url)

            return (
              <TooltipProvider key={index}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="relative flex-shrink-0 hover:z-10 transition-transform hover:scale-110"
                      style={{ marginLeft: index > 0 ? '-6px' : '0' }}
                    >
                      <div className="h-5 w-5 rounded-full border-2 border-background bg-background flex items-center justify-center overflow-hidden shadow-sm">
                        {faviconUrl ? (
                          <img
                            src={faviconUrl}
                            alt={hostname}
                            className="h-4 w-4 rounded-sm"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        ) : (
                          <div className="h-4 w-4 rounded-sm bg-muted flex items-center justify-center text-[9px] font-medium text-muted-foreground">
                            {hostname.charAt(0).toUpperCase()}
                          </div>
                        )}
                      </div>
                    </a>
                  </TooltipTrigger>
                  <TooltipPortal>
                    <TooltipContent
                      side="bottom"
                      align="start"
                      sideOffset={6}
                      className="max-w-xs"
                    >
                      <span className="font-medium">
                        {source.title || getDomainName(source.url)}
                      </span>
                    </TooltipContent>
                  </TooltipPortal>
                </Tooltip>
              </TooltipProvider>
            )
          })}
        </div>

        {/* Sources button */}
        <button
          onClick={() => setIsOpen(true)}
          className="text-xs text-muted-foreground font-medium hover:text-foreground transition-colors"
        >
          Sources
        </button>
      </div>

      {/* Desktop: Dialog modal */}
      {!isMobile && (
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
          <DialogContent className="max-w-md p-0 gap-0">
            <DialogHeader className="px-5 pt-5 pb-4 border-b border-border">
              <DialogTitle className="text-base font-semibold">
                Sources
              </DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                {sources.length} reference{sources.length !== 1 ? 's' : ''} cited
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-[60vh] overflow-y-auto p-2">
              {SourcesList}
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Mobile: Bottom sheet */}
      {isMobile && (
        <Sheet open={isOpen} onOpenChange={setIsOpen}>
          <SheetContent
            side="bottom"
            className="h-[70vh] rounded-t-2xl border-t-2 border-t-accent-brand p-0"
          >
            {/* Drag handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
            </div>

            <SheetHeader className="px-4 pb-3 border-b border-border">
              <SheetTitle className="text-base">Sources</SheetTitle>
              <SheetDescription>
                {sources.length} reference{sources.length !== 1 ? 's' : ''} cited
              </SheetDescription>
            </SheetHeader>

            <ScrollArea className="flex-1 h-[calc(70vh-90px)]">
              <div className="p-4">
                {SourcesList}
              </div>
            </ScrollArea>
          </SheetContent>
        </Sheet>
      )}
    </>
  )
}
