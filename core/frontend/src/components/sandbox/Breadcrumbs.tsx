/**
 * Breadcrumbs - File path navigation
 */

import { memo } from 'react'
import { ChevronRight, Folder, FileCode } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FileIcon } from './FileIcon'

interface BreadcrumbsProps {
  filePath: string
  onNavigate?: (path: string) => void
  className?: string
}

export const Breadcrumbs = memo(function Breadcrumbs({
  filePath,
  onNavigate,
  className,
}: BreadcrumbsProps) {
  // Split path into segments
  const segments = filePath.split('/').filter(Boolean)

  // Build paths for each segment
  const pathSegments = segments.map((segment, index) => ({
    name: segment,
    path: '/' + segments.slice(0, index + 1).join('/'),
    isLast: index === segments.length - 1,
  }))

  if (pathSegments.length === 0) return null

  return (
    <div
      className={cn(
        "flex items-center gap-1 px-4 py-1.5 text-xs text-muted-foreground bg-muted/20 border-b border-border/30 overflow-x-auto",
        className
      )}
    >
      {pathSegments.map((segment, index) => (
        <div key={segment.path} className="flex items-center gap-1 shrink-0">
          {index > 0 && (
            <ChevronRight className="h-3 w-3 text-muted-foreground/50" />
          )}

          <button
            onClick={() => onNavigate?.(segment.path)}
            className={cn(
              "flex items-center gap-1.5 px-1.5 py-0.5 rounded hover:bg-muted/50 transition-colors",
              segment.isLast && "text-foreground font-medium"
            )}
          >
            {segment.isLast ? (
              <FileIcon filename={segment.name} className="h-3.5 w-3.5" />
            ) : (
              <Folder className="h-3.5 w-3.5 text-accent-brand/70" />
            )}
            <span className="max-w-[150px] truncate">{segment.name}</span>
          </button>
        </div>
      ))}
    </div>
  )
})
