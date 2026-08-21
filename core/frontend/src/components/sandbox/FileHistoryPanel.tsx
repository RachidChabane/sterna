/**
 * FileHistoryPanel Component
 *
 * Shows version history for a single file with ability to view and compare versions.
 * Displays source type (user edit, file tool, coding agent), timestamps, and allows
 * selecting versions for comparison.
 */

import React, { useState, useEffect } from 'react'
import { formatDistanceToNow } from 'date-fns'
import {
  History,
  User,
  Bot,
  Code,
  Upload,
  RotateCcw,
  FileText,
  Eye,
  GitCompare,
  Loader2,
  Trash2,
  File,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { versionsApi, type FileVersion } from '@/api/versions'

interface FileHistoryPanelProps {
  chatId: string
  filePath: string
  onViewVersion: (version: FileVersion) => void
  onCompareVersions: (versionA: FileVersion, versionB: FileVersion) => void
  className?: string
}

const SOURCE_TYPE_CONFIG: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  user_edit: { icon: User, label: 'User Edit', color: 'text-blue-500' },
  file_tool: { icon: Code, label: 'File Tool', color: 'text-purple-500' },
  coding_agent: { icon: Bot, label: 'Coding Agent', color: 'text-green-500' },
  upload: { icon: Upload, label: 'Upload', color: 'text-orange-500' },
  restore: { icon: RotateCcw, label: 'Restore', color: 'text-gray-500' },
  initial: { icon: FileText, label: 'Initial', color: 'text-gray-400' },
}

export function FileHistoryPanel({
  chatId,
  filePath,
  onViewVersion,
  onCompareVersions,
  className,
}: FileHistoryPanelProps) {
  const [versions, setVersions] = useState<FileVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedVersions, setSelectedVersions] = useState<Set<string>>(new Set())

  useEffect(() => {
    loadHistory()
  }, [chatId, filePath])

  const loadHistory = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await versionsApi.getFileHistory(chatId, filePath)
      setVersions(response.data.versions)
    } catch (err) {
      setError('Failed to load file history')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const toggleVersionSelection = (versionId: string) => {
    const newSelected = new Set(selectedVersions)
    if (newSelected.has(versionId)) {
      newSelected.delete(versionId)
    } else if (newSelected.size < 2) {
      newSelected.add(versionId)
    }
    setSelectedVersions(newSelected)
  }

  const handleCompare = () => {
    const selectedArray = Array.from(selectedVersions)
    if (selectedArray.length === 2) {
      const versionA = versions.find(v => v.id === selectedArray[0])
      const versionB = versions.find(v => v.id === selectedArray[1])
      if (versionA && versionB) {
        // Ensure older version is first
        const [older, newer] = versionA.version_number < versionB.version_number
          ? [versionA, versionB]
          : [versionB, versionA]
        onCompareVersions(older, newer)
      }
    }
  }

  if (loading) {
    return (
      <div className={cn('flex items-center justify-center p-8', className)}>
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className={cn('p-4 text-center text-destructive', className)}>
        {error}
        <Button variant="outline" size="sm" onClick={loadHistory} className="mt-2">
          Retry
        </Button>
      </div>
    )
  }

  if (versions.length === 0) {
    return (
      <div className={cn('p-4 text-center text-muted-foreground', className)}>
        <History className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No version history available</p>
      </div>
    )
  }

  const filename = filePath.split('/').pop() || filePath

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b bg-muted/50">
        <History className="h-4 w-4 text-muted-foreground" />
        <span className="font-medium truncate flex-1">{filename}</span>
        <span className="text-xs text-muted-foreground">
          {versions.length} version{versions.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Compare button */}
      {selectedVersions.size === 2 && (
        <div className="p-2 border-b bg-muted/30">
          <Button
            size="sm"
            onClick={handleCompare}
            className="w-full"
          >
            <GitCompare className="h-4 w-4 mr-2" />
            Compare Selected
          </Button>
        </div>
      )}

      {/* Version list */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {versions.map((version, index) => {
            const config = SOURCE_TYPE_CONFIG[version.source_type] || { icon: File, label: 'Unknown', color: 'text-gray-500' }
            const Icon = config.icon
            const isSelected = selectedVersions.has(version.id)
            const prevVersion = versions[index + 1] // Older version (lower number)

            return (
              <div
                key={version.id}
                className={cn(
                  'group rounded-md border p-2 transition-colors',
                  isSelected ? 'border-primary bg-primary/5' : 'border-transparent hover:bg-muted/50'
                )}
              >
                <div className="flex items-start gap-2">
                  {/* Selection checkbox */}
                  <button
                    onClick={() => toggleVersionSelection(version.id)}
                    className={cn(
                      'mt-0.5 h-4 w-4 rounded border flex items-center justify-center transition-colors flex-shrink-0',
                      isSelected
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-muted-foreground/30 hover:border-muted-foreground'
                    )}
                  >
                    {isSelected && <span className="text-xs">✓</span>}
                  </button>

                  {/* Version info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Icon className={cn('h-3.5 w-3.5 flex-shrink-0', config.color)} />
                      <span className="text-sm font-medium">v{version.version_number}</span>
                      {version.is_deleted && (
                        <Trash2 className="h-3 w-3 text-destructive flex-shrink-0" />
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {config.label}
                      {version.source_tool_name && ` (${version.source_tool_name})`}
                      {version.source_job_id && ` • Job ${version.source_job_id.slice(0, 8)}`}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatDistanceToNow(new Date(version.created_at), { addSuffix: true })}
                      {version.created_by && ` by ${version.created_by.username}`}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => onViewVersion(version)}
                      disabled={version.is_binary}
                      title="View content"
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </Button>
                    {prevVersion && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => onCompareVersions(prevVersion, version)}
                        disabled={version.is_binary || prevVersion.is_binary}
                        title="Compare with previous"
                      >
                        <GitCompare className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}

export default FileHistoryPanel
