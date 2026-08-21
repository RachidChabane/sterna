/**
 * VersionDiffModal Component
 *
 * Modal dialog showing Monaco diff viewer for comparing two file versions.
 * Fetches version content from API and displays side-by-side diff.
 */

import React, { useState, useEffect, Suspense, lazy } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { X, Loader2, AlertCircle, GitCompare } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { versionsApi, type FileVersion, type CompareVersionsResponse } from '@/api/versions'

// Monaco Editor's diff viewer is only needed once a comparison is actually
// shown, so it's split into its own chunk instead of shipping with the
// main bundle.
const MonacoDiffViewer = lazy(() =>
  import('@/components/sandbox/MonacoDiffViewer').then((module) => ({
    default: module.MonacoDiffViewer,
  })),
)

interface VersionDiffModalProps {
  isOpen: boolean
  onClose: () => void
  versionA: FileVersion | null  // Older version (original)
  versionB: FileVersion | null  // Newer version (modified)
  /** Optional: pre-loaded comparison result (skip API call) */
  preloadedComparison?: CompareVersionsResponse
}

export function VersionDiffModal({
  isOpen,
  onClose,
  versionA,
  versionB,
  preloadedComparison,
}: VersionDiffModalProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [comparison, setComparison] = useState<CompareVersionsResponse | null>(preloadedComparison || null)

  useEffect(() => {
    if (isOpen && versionA && versionB && !preloadedComparison) {
      loadComparison()
    } else if (preloadedComparison) {
      setComparison(preloadedComparison)
    }
  }, [isOpen, versionA?.id, versionB?.id, preloadedComparison])

  const loadComparison = async () => {
    if (!versionA || !versionB) return

    setLoading(true)
    setError(null)
    setComparison(null)

    try {
      const response = await versionsApi.compareVersions(versionA.id, versionB.id)
      setComparison(response.data)
    } catch (err) {
      setError('Failed to load version comparison')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    setComparison(null)
    setError(null)
    onClose()
  }

  const filename = versionA?.path.split('/').pop() || versionB?.path.split('/').pop() || 'Unknown'
  const filePath = versionA?.path || versionB?.path || ''

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="max-w-6xl w-[95vw] h-[85vh] flex flex-col p-0">
        <DialogHeader className="px-4 py-3 border-b flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GitCompare className="h-5 w-5 text-muted-foreground" />
              <DialogTitle className="text-base">
                Comparing {filename}
              </DialogTitle>
            </div>
            <Button variant="ghost" size="icon" onClick={handleClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          <DialogDescription className="sr-only">
            Compare file versions side by side
          </DialogDescription>

          {versionA && versionB && (
            <div className="flex items-center gap-4 text-xs text-muted-foreground mt-2 flex-wrap">
              <div className="flex items-center gap-1">
                <span className="font-medium text-red-500">v{versionA.version_number}</span>
                <span className="hidden sm:inline">
                  ({formatDistanceToNow(new Date(versionA.created_at), { addSuffix: true })})
                </span>
              </div>
              <span>→</span>
              <div className="flex items-center gap-1">
                <span className="font-medium text-green-500">v{versionB.version_number}</span>
                <span className="hidden sm:inline">
                  ({formatDistanceToNow(new Date(versionB.created_at), { addSuffix: true })})
                </span>
              </div>
            </div>
          )}
        </DialogHeader>

        <div className="flex-1 min-h-0 p-4">
          {loading && (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="h-full flex flex-col items-center justify-center gap-2 text-destructive">
              <AlertCircle className="h-8 w-8" />
              <span>{error}</span>
              <Button variant="outline" size="sm" onClick={loadComparison}>
                Retry
              </Button>
            </div>
          )}

          {comparison && comparison.is_binary && (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              <div className="text-center">
                <AlertCircle className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Cannot display diff for binary files</p>
              </div>
            </div>
          )}

          {comparison && !comparison.is_binary && (
            <Suspense
              fallback={
                <div className="h-full flex items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              }
            >
              <MonacoDiffViewer
                originalContent={comparison.original_content || ''}
                modifiedContent={comparison.modified_content || ''}
                filePath={filePath}
                originalLabel={`v${comparison.version_a.version_number} (${comparison.version_a.source_type_display})`}
                modifiedLabel={`v${comparison.version_b.version_number} (${comparison.version_b.source_type_display})`}
                className="h-full rounded-md border overflow-hidden"
              />
            </Suspense>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default VersionDiffModal
