/**
 * ToolDetailsModal Component
 *
 * Shows details about an MCP tool including its description and input schema.
 */

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Globe, Braces, FileText, Loader2 } from 'lucide-react'
import type { MCPServer, MCPToolMinimal, MCPTool } from '@/api/mcp'
import { mcpApi } from '@/api/mcp'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface ToolDetailsModalProps {
  isOpen: boolean
  onClose: () => void
  tool: MCPToolMinimal | null
  server: MCPServer | null
}

/**
 * Format JSON schema property for display
 */
function formatSchemaProperty(name: string, prop: Record<string, unknown>, required: boolean) {
  const type = prop.type as string || 'any'
  const description = prop.description as string
  const enumValues = prop.enum as string[]

  return (
    <div key={name} className="py-2 first:pt-0 last:pb-0">
      <div className="flex items-center gap-2 mb-1">
        <code className="text-sm font-mono text-foreground bg-muted px-1.5 py-0.5 rounded">
          {name}
        </code>
        <Badge variant="outline" className="text-[10px] font-mono">
          {type}
        </Badge>
        {required && (
          <Badge className="text-[10px] bg-amber-500/20 text-amber-600 dark:text-amber-400 border-0">
            required
          </Badge>
        )}
      </div>
      {description && (
        <p className="text-sm text-muted-foreground ml-0.5">{description}</p>
      )}
      {enumValues && enumValues.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5 ml-0.5">
          {enumValues.map((val) => (
            <code key={val} className="text-xs bg-secondary px-1.5 py-0.5 rounded text-muted-foreground">
              {val}
            </code>
          ))}
        </div>
      )}
    </div>
  )
}

export function ToolDetailsModal({
  isOpen,
  onClose,
  tool,
  server,
}: ToolDetailsModalProps) {
  const [fullTool, setFullTool] = useState<MCPTool | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch full tool data when modal opens
  useEffect(() => {
    if (isOpen && tool?.id) {
      setLoading(true)
      setError(null)
      mcpApi.getTool(tool.id)
        .then(response => {
          setFullTool(response.data)
        })
        .catch(err => {
          console.error('Failed to fetch tool details:', err)
          setError('Failed to load tool details')
        })
        .finally(() => {
          setLoading(false)
        })
    } else if (!isOpen) {
      // Reset state when modal closes
      setFullTool(null)
      setError(null)
    }
  }, [isOpen, tool?.id])

  if (!tool) return null

  // Parse input schema from full tool data
  const inputSchema = fullTool?.input_schema || {}
  const properties = (inputSchema.properties || {}) as Record<string, Record<string, unknown>>
  const required = (inputSchema.required || []) as string[]
  const hasParameters = Object.keys(properties).length > 0

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[85vh] p-0 gap-0 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 p-5 pb-4 border-b border-border">
          <DialogHeader>
            <div className="flex items-start gap-3">
              {/* Server icon */}
              <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-muted flex items-center justify-center">
                {server?.icon_url ? (
                  <img
                    src={server.icon_url}
                    alt=""
                    className="w-6 h-6 object-contain"
                  />
                ) : (
                  <Globe className="w-5 h-5 text-muted-foreground" />
                )}
              </div>

              <div className="flex-1 min-w-0">
                <DialogTitle className="text-base font-semibold leading-tight">
                  {tool.name}
                </DialogTitle>
                {server && (
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {server.name}
                  </p>
                )}
              </div>
            </div>
          </DialogHeader>
        </div>

        {/* Content */}
        <ScrollArea className="flex-1 min-h-0">
          <div className="p-5 space-y-5">
            {/* Description */}
            {tool.description && (
              <div className="w-full overflow-hidden">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-2">
                  <FileText className="w-4 h-4" />
                  Description
                </div>
                <div className="w-full overflow-hidden text-sm text-foreground leading-relaxed prose prose-sm prose-neutral dark:prose-invert max-w-none prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-code:text-xs prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:my-1.5 prose-pre:overflow-x-auto">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {tool.description}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Parameters */}
            {!loading && !error && hasParameters && (
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-3">
                  <Braces className="w-4 h-4" />
                  Parameters
                </div>
                <div className="rounded-lg border border-border bg-muted/30 p-3 divide-y divide-border/50">
                  {Object.entries(properties).map(([name, prop]) =>
                    formatSchemaProperty(name, prop, required.includes(name))
                  )}
                </div>
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
            )}

            {/* Error state */}
            {error && !loading && (
              <div className="text-sm text-destructive text-center py-4">
                {error}
              </div>
            )}

            {/* No parameters */}
            {!loading && !error && fullTool && !hasParameters && (
              <div className="text-sm text-muted-foreground text-center py-4">
                This tool has no parameters
              </div>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
