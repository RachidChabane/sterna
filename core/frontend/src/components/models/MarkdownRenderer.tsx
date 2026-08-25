/**
 * MarkdownRenderer - Renders markdown content for Spark display
 *
 * Reuses the existing Markdown component from the chat message rendering.
 * Wraps in a styled container with proper typography.
 */

import React from 'react'
import { cn } from '@/lib/utils'
import { Markdown } from '@/components/ui/markdown'

interface MarkdownRendererProps {
  code: string
  className?: string
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  code,
  className,
}) => {
  return (
    <div className={cn(
      'rounded-lg border bg-background overflow-auto p-6',
      className
    )}>
      <Markdown className="max-w-none">
        {code}
      </Markdown>
    </div>
  )
}
