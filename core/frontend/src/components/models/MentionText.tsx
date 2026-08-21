/**
 * MentionText Component
 *
 * Renders text with @server and @server:tool mentions styled as elegant inline tags.
 * Also supports @knowledge mentions for Knowledge Base queries.
 * Supports enriched coding agent mentions:
 *   @plan_implementation #42 Issue Title
 *   @implement_plan plan:uuid Plan Title
 *   @edit_plan plan:uuid Plan Title
 * Clicking a mention opens a modal with tool details.
 */

import { memo, useMemo, useState, useCallback } from 'react'
import { BookOpen, Terminal, ImageIcon, Video, Clapperboard, UserRound, BrainCircuit } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CODING_AGENT_DISPLAY_NAMES, MEDIA_TOOL_DISPLAY_NAMES } from '@/hooks/useMentionAutocomplete'
import { useMCPStore } from '@/store/mcpStore'
import { ToolDetailsModal } from './ToolDetailsModal'
import { ServerDetailModal } from '@/components/mcp/ServerDetailModal'
import { mcpApi } from '@/api/mcp'
import type { MCPServer, MCPToolMinimal, MCPPreconfiguredServer } from '@/api/mcp'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface MentionTextProps {
  children: string
  className?: string
}

interface TextPart {
  type: 'text' | 'mention' | 'knowledge' | 'coding_agent' | 'media_tool'
  content: string
  serverName?: string
  toolName?: string
  serverIcon?: string
  server?: MCPServer
  tool?: MCPToolMinimal
  issueNumber?: number
  issueTitle?: string
  planId?: string
  planTitle?: string
  agentSlug?: string
  mediaParams?: Record<string, string>
}

// Coding agent tool names that support enriched mentions
const CODING_AGENT_NAMES = ['coding_agent', 'plan_implementation', 'implement_plan', 'edit_plan']

// Media tool names
const MEDIA_TOOL_NAMES = ['generate_image', 'generate_video', 'animate_image', 'animate_character']

/**
 * Parse text and split into text, mention, and knowledge parts.
 * Handles enriched coding agent mentions with issue/plan references.
 */
function parseTextWithMentions(text: string, servers: MCPServer[]): TextPart[] {
  const parts: TextPart[] = []

  // Track consumed ranges from enriched mentions (pre-pass)
  const consumedRanges: Array<{ start: number; end: number; part: TextPart }> = []

  // Pre-pass: match coding agent mentions with delegation instruction
  // e.g. @coding_agent Delegate to the "security-reviewer" sub-agent.
  const agentDelegatePattern = /@(coding_agent|plan_implementation|implement_plan|edit_plan)\s+Delegate to the "([^"]+)" sub-agent\./g
  let agentSlugMatch: RegExpExecArray | null
  while ((agentSlugMatch = agentDelegatePattern.exec(text)) !== null) {
    consumedRanges.push({
      start: agentSlugMatch.index,
      end: agentSlugMatch.index + agentSlugMatch[0].length,
      part: {
        type: 'coding_agent',
        content: agentSlugMatch[0],
        serverName: agentSlugMatch[1],
        agentSlug: agentSlugMatch[2],
      }
    })
  }

  // Pre-pass: match enriched coding agent mentions
  // @plan_implementation #123 Issue Title (terminated by next @ or end of string)
  const issuePattern = /@(plan_implementation)\s+#(\d+)\s+(.+?)(?=\s*@|\s*$)/g
  let enrichedMatch: RegExpExecArray | null
  while ((enrichedMatch = issuePattern.exec(text)) !== null) {
    consumedRanges.push({
      start: enrichedMatch.index,
      end: enrichedMatch.index + enrichedMatch[0].length,
      part: {
        type: 'coding_agent',
        content: enrichedMatch[0],
        serverName: enrichedMatch[1],
        issueNumber: parseInt(enrichedMatch[2], 10),
        issueTitle: enrichedMatch[3].trim(),
      }
    })
  }

  // @implement_plan plan:uuid Title  or  @edit_plan plan:uuid Title
  const planPattern = /@(implement_plan|edit_plan)\s+plan:([a-f0-9-]+)\s+(.+?)(?=\s*@|\s*$)/g
  while ((enrichedMatch = planPattern.exec(text)) !== null) {
    consumedRanges.push({
      start: enrichedMatch.index,
      end: enrichedMatch.index + enrichedMatch[0].length,
      part: {
        type: 'coding_agent',
        content: enrichedMatch[0],
        serverName: enrichedMatch[1],
        planId: enrichedMatch[2],
        planTitle: enrichedMatch[3].trim(),
      }
    })
  }

  // Pre-pass: match media tool mentions with bracket params
  // @generate_image [model:X ratio:Y res:Z] or @generate_video [model:X ratio:Y dur:Z quality:W]
  const mediaPattern = /@(generate_image|generate_video|animate_image|animate_character)\s+\[([^\]]*)\]/g
  while ((enrichedMatch = mediaPattern.exec(text)) !== null) {
    const params: Record<string, string> = {}
    for (const pair of enrichedMatch[2].split(/\s+/)) {
      if (pair.includes(':')) {
        const [key, ...valueParts] = pair.split(':')
        params[key] = valueParts.join(':')
      }
    }
    consumedRanges.push({
      start: enrichedMatch.index,
      end: enrichedMatch.index + enrichedMatch[0].length,
      part: {
        type: 'media_tool',
        content: enrichedMatch[0],
        serverName: enrichedMatch[1],
        mediaParams: params,
      }
    })
  }

  // Sort consumed ranges by start position
  consumedRanges.sort((a, b) => a.start - b.start)

  // Main pass: match @server_name or @server_name:tool_name, skipping consumed ranges
  const pattern = /(?:^|(?<=[\s.,!?;:'"()\[\]{}]))@([a-zA-Z0-9_-]+)(?::([a-zA-Z0-9_-]+))?/g

  let lastIndex = 0
  let match: RegExpExecArray | null

  // Build a set of positions to skip
  const isConsumed = (pos: number) =>
    consumedRanges.some(r => pos >= r.start && pos < r.end)

  // Process in order: merge consumed ranges with regex matches
  const allEvents: Array<{ start: number; end: number; part: TextPart }> = [...consumedRanges]

  // Add regex matches that don't overlap with consumed ranges
  while ((match = pattern.exec(text)) !== null) {
    if (isConsumed(match.index)) continue

    const serverName = match[1]
    const toolName = match[2] || undefined

    let part: TextPart

    if (serverName.toLowerCase() === 'knowledge') {
      part = {
        type: 'knowledge',
        content: match[0],
        serverName: 'knowledge',
      }
    } else if (MEDIA_TOOL_NAMES.includes(serverName.toLowerCase())) {
      part = {
        type: 'media_tool',
        content: match[0],
        serverName,
      }
    } else if (CODING_AGENT_NAMES.includes(serverName.toLowerCase())) {
      part = {
        type: 'coding_agent',
        content: match[0],
        serverName,
      }
    } else {
      const matchingServer = servers.find(
        s => s.name.toLowerCase() === serverName.toLowerCase()
      )
      let matchingTool: MCPToolMinimal | undefined
      if (toolName && matchingServer?.tools) {
        matchingTool = matchingServer.tools.find(
          t => t.name.toLowerCase() === toolName.toLowerCase()
        )
      }
      part = {
        type: 'mention',
        content: match[0],
        serverName,
        toolName,
        serverIcon: matchingServer?.icon_url || undefined,
        server: matchingServer,
        tool: matchingTool,
      }
    }

    allEvents.push({
      start: match.index,
      end: match.index + match[0].length,
      part,
    })
  }

  // Sort all events by position
  allEvents.sort((a, b) => a.start - b.start)

  // Build parts array
  lastIndex = 0
  for (const event of allEvents) {
    if (event.start < lastIndex) continue // skip overlapping

    if (event.start > lastIndex) {
      parts.push({
        type: 'text',
        content: text.slice(lastIndex, event.start),
      })
    }

    parts.push(event.part)
    lastIndex = event.end
  }

  if (lastIndex < text.length) {
    parts.push({
      type: 'text',
      content: text.slice(lastIndex),
    })
  }

  return parts
}

function MentionTextComponent({ children, className }: MentionTextProps) {
  const servers = useMCPStore(state => state.servers)

  // Tool modal state
  const [toolModalOpen, setToolModalOpen] = useState(false)
  const [selectedTool, setSelectedTool] = useState<MCPToolMinimal | null>(null)
  const [selectedToolServer, setSelectedToolServer] = useState<MCPServer | null>(null)

  // Server modal state
  const [serverModalOpen, setServerModalOpen] = useState(false)
  const [selectedPreconfiguredServer, setSelectedPreconfiguredServer] = useState<MCPPreconfiguredServer | null>(null)

  const parts = useMemo(() => {
    if (!children || typeof children !== 'string') return []
    return parseTextWithMentions(children, servers)
  }, [children, servers])

  const handleMentionClick = useCallback(async (part: TextPart) => {
    if (part.tool && part.server) {
      // Tool mention - show tool modal
      setSelectedTool(part.tool)
      setSelectedToolServer(part.server)
      setToolModalOpen(true)
    } else if (part.server && !part.tool) {
      // Server-only mention - fetch preconfigured server and show modal
      try {
        const response = await mcpApi.listPreconfiguredServers()
        const preconfigured = response.data.results.find(
          s => s.name.toLowerCase() === part.serverName?.toLowerCase()
        )
        if (preconfigured) {
          setSelectedPreconfiguredServer(preconfigured)
          setServerModalOpen(true)
        }
      } catch (err) {
        console.error('Failed to fetch preconfigured server:', err)
      }
    }
  }, [])

  const handleCloseToolModal = useCallback(() => {
    setToolModalOpen(false)
    setSelectedTool(null)
    setSelectedToolServer(null)
  }, [])

  const handleCloseServerModal = useCallback(() => {
    setServerModalOpen(false)
    setSelectedPreconfiguredServer(null)
  }, [])

  if (parts.length === 0) {
    return <span className={className}>{children}</span>
  }

  return (
    <>
      <TooltipProvider delayDuration={200}>
        <span className={className}>
          {parts.map((part, index) => {
            if (part.type === 'text') {
              return <span key={index}>{part.content}</span>
            }

            // Knowledge Base mention - show icon with tooltip
            if (part.type === 'knowledge') {
              return (
                <Tooltip key={index}>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center gap-1 font-semibold text-emerald-600 dark:text-emerald-400">
                      <BookOpen className="w-4 h-4" />
                      <span>knowledge</span>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">
                    Search your Knowledge Base
                  </TooltipContent>
                </Tooltip>
              )
            }

            // Media tool mention - show icon with params
            if (part.type === 'media_tool') {
              const toolName = part.serverName?.toLowerCase() || ''
              const toolDisplayName = (part.serverName && MEDIA_TOOL_DISPLAY_NAMES[part.serverName]) || part.serverName
              const iconMap: Record<string, typeof Video> = {
                generate_image: ImageIcon,
                generate_video: Video,
                animate_image: Clapperboard,
                animate_character: UserRound,
              }
              const Icon = iconMap[toolName] || Video

              if (part.mediaParams && Object.keys(part.mediaParams).length > 0) {
                // Enriched media mention with params
                return (
                  <Tooltip key={index}>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-1 font-semibold text-purple-500">
                        <Icon className="w-4 h-4" />
                        <span>{toolDisplayName}</span>
                        <span className="text-xs opacity-60 font-normal">
                          [{Object.entries(part.mediaParams).map(([k, v]) => `${k}:${v}`).join(' ')}]
                        </span>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs max-w-xs">
                      <div>{toolDisplayName}</div>
                      <div className="text-muted-foreground">
                        {Object.entries(part.mediaParams).map(([k, v]) => (
                          <span key={k} className="mr-2">{k}: {v}</span>
                        ))}
                      </div>
                    </TooltipContent>
                  </Tooltip>
                )
              }

              // Plain media tool mention (no params)
              return (
                <Tooltip key={index}>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center gap-1 font-semibold text-purple-500">
                      <Icon className="w-4 h-4" />
                      <span>{toolDisplayName}</span>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">
                    {toolDisplayName}
                  </TooltipContent>
                </Tooltip>
              )
            }

            // Coding Agent tool mention - show icon with tooltip
            if (part.type === 'coding_agent') {
              const toolDisplayName = (part.serverName && CODING_AGENT_DISPLAY_NAMES[part.serverName]) || part.serverName

              // Enriched mention with issue reference
              if (part.issueNumber) {
                return (
                  <Tooltip key={index}>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-1 font-semibold text-accent-brand">
                        <Terminal className="w-4 h-4" />
                        <span>{toolDisplayName}</span>
                        <span className="font-mono text-xs opacity-75">#{part.issueNumber}</span>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs max-w-xs">
                      <div>{toolDisplayName} — Issue #{part.issueNumber}</div>
                      {part.issueTitle && <div className="text-muted-foreground">{part.issueTitle}</div>}
                    </TooltipContent>
                  </Tooltip>
                )
              }

              // Enriched mention with plan reference
              if (part.planId) {
                return (
                  <Tooltip key={index}>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-1 font-semibold text-accent-brand">
                        <Terminal className="w-4 h-4" />
                        <span>{toolDisplayName}</span>
                        {part.planTitle && (
                          <span className="text-xs opacity-75">{part.planTitle}</span>
                        )}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs max-w-xs">
                      <div>{toolDisplayName} — Plan</div>
                      {part.planTitle && <div className="text-muted-foreground">{part.planTitle}</div>}
                    </TooltipContent>
                  </Tooltip>
                )
              }

              // Enriched mention with agent:slug qualifier
              if (part.agentSlug) {
                return (
                  <Tooltip key={index}>
                    <TooltipTrigger asChild>
                      <span className="inline-flex items-center gap-1 font-semibold text-accent-brand">
                        <Terminal className="w-4 h-4" />
                        <span>{toolDisplayName}</span>
                        <span className="inline-flex items-center gap-0.5 text-xs opacity-75">
                          <BrainCircuit className="w-3 h-3" />
                          {part.agentSlug}
                        </span>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="text-xs max-w-xs">
                      <div>{toolDisplayName} — Agent: {part.agentSlug}</div>
                    </TooltipContent>
                  </Tooltip>
                )
              }

              // Plain coding agent mention (no enrichment)
              return (
                <Tooltip key={index}>
                  <TooltipTrigger asChild>
                    <span className="inline-flex items-center gap-1 font-semibold text-accent-brand">
                      <Terminal className="w-4 h-4" />
                      <span>{toolDisplayName}</span>
                    </span>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">
                    Coding Agent Tool
                  </TooltipContent>
                </Tooltip>
              )
            }

            const isClickable = Boolean(part.tool) || Boolean(part.server)

            // Mention tag - subtle inline style
            return (
              <span
                key={index}
                onClick={isClickable ? () => handleMentionClick(part) : undefined}
                className={cn(
                  "inline-flex items-center gap-1 font-semibold border-b border-current/30",
                  isClickable && "cursor-pointer hover:border-current/60 transition-colors"
                )}
              >
                {/* Server icon */}
                {part.serverIcon && (
                  <img
                    src={part.serverIcon}
                    alt=""
                    className="w-4 h-4 object-contain opacity-90"
                  />
                )}

                {/* Mention text */}
                {part.toolName ? (
                  <>{part.serverName}/{part.toolName}</>
                ) : (
                  <>{part.serverName}</>
                )}
              </span>
            )
          })}
        </span>
      </TooltipProvider>

      <ToolDetailsModal
        isOpen={toolModalOpen}
        onClose={handleCloseToolModal}
        tool={selectedTool}
        server={selectedToolServer}
      />

      <ServerDetailModal
        isOpen={serverModalOpen}
        onClose={handleCloseServerModal}
        server={selectedPreconfiguredServer}
        isConnected={true}
      />
    </>
  )
}

export const MentionText = memo(MentionTextComponent)
