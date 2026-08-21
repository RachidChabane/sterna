/**
 * ConnectorsHoverCard Component
 *
 * Displays a list of active integrations in a hover card with pagination
 */

import { useState } from 'react'
import { Puzzle, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card'
import { Link } from '@tanstack/react-router'
import type { MCPServer } from '@/api/mcp'

interface ConnectorsHoverCardProps {
  children: React.ReactNode
  activeServers: MCPServer[]
  enabled: number
  total: number
  supported: number
}

const ITEMS_PER_PAGE = 5

export function ConnectorsHoverCard({
  children,
  activeServers,
  enabled,
  total,
  supported,
}: ConnectorsHoverCardProps) {
  const [currentPage, setCurrentPage] = useState(0)

  // Reset page when servers change
  const totalPages = Math.ceil(activeServers.length / ITEMS_PER_PAGE)
  const safePage = Math.min(currentPage, Math.max(0, totalPages - 1))
  const startIdx = safePage * ITEMS_PER_PAGE
  const endIdx = Math.min(startIdx + ITEMS_PER_PAGE, activeServers.length)
  const visibleServers = activeServers.slice(startIdx, endIdx)

  const allCompatibleEnabled = enabled === supported && supported > 0
  const someEnabled = enabled > 0 && enabled < supported

  if (supported === 0) {
    return (
      <HoverCard openDelay={200}>
        <HoverCardTrigger asChild>
          {children}
        </HoverCardTrigger>
        <HoverCardContent className="w-80 p-3" side="top">
          <div className="text-center py-4">
            <p className="font-medium text-sm">No Function-Capable Models</p>
            <p className="text-xs text-muted-foreground mt-1">
              Select a model that supports function calling to enable integrations
            </p>
          </div>
        </HoverCardContent>
      </HoverCard>
    )
  }

  if (activeServers.length === 0) {
    return (
      <HoverCard openDelay={200}>
        <HoverCardTrigger asChild>
          {children}
        </HoverCardTrigger>
        <HoverCardContent className="w-80 p-3" side="top">
          <div className="text-center py-4">
            <p className="font-medium text-sm">No Connectors Available</p>
            <p className="text-xs text-muted-foreground mt-1">
              Add connectors to connect to external tools
            </p>
          </div>
        </HoverCardContent>
      </HoverCard>
    )
  }

  return (
    <HoverCard openDelay={200}>
      <HoverCardTrigger asChild>
        {children}
      </HoverCardTrigger>
      <HoverCardContent className="w-80 p-3" side="top">
        <div className="space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between border-b pb-2">
            <div>
              <p className="font-medium text-sm">
                {allCompatibleEnabled
                  ? 'Active Connectors'
                  : someEnabled
                  ? `${enabled}/${total} Chats Active`
                  : 'Available Connectors'}
              </p>
              <p className="text-xs text-muted-foreground">
                {activeServers.length} integration{activeServers.length !== 1 ? 's' : ''}
              </p>
            </div>
            <Link to="/connectors">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 gap-1.5"
              >
                <span className="text-xs">View All</span>
                <ExternalLink className="h-3 w-3" />
              </Button>
            </Link>
          </div>

          {/* Servers List */}
          <div className="space-y-2">
            {visibleServers.map((server) => (
              <Link
                key={server.id}
                to="/connectors"
                className="flex items-center gap-2 p-2 rounded-md bg-muted/50 hover:bg-muted transition-colors cursor-pointer"
              >
                {server.icon_url ? (
                  <img
                    src={server.icon_url}
                    alt={server.name}
                    className="h-4 w-4 rounded object-cover flex-shrink-0"
                  />
                ) : (
                  <Puzzle className="h-4 w-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">{server.name}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {server.transport_type}
                  </p>
                </div>
                {server.is_active && (
                  <div className="h-2 w-2 rounded-full bg-green-500 flex-shrink-0" />
                )}
              </Link>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2 border-t">
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  setCurrentPage(Math.max(0, safePage - 1))
                }}
                disabled={safePage === 0}
                className="h-7 px-2"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs text-muted-foreground">
                {safePage + 1} / {totalPages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  setCurrentPage(Math.min(totalPages - 1, safePage + 1))
                }}
                disabled={safePage === totalPages - 1}
                className="h-7 px-2"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  )
}
