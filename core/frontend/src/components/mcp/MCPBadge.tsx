/**
 * MCPBadge Component
 *
 * Displays a button showing connected servers.
 * Clicking the button navigates to the MCP page.
 */

import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Wrench } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useMCPStore } from '@/store/mcpStore'
import { cn } from '@/lib/utils'

interface MCPBadgeProps {
  className?: string
  onClick?: () => void
}

export function MCPBadge({ className, onClick }: MCPBadgeProps) {
  const navigate = useNavigate()
  const {
    servers,
    tools,
    getActiveServers,
    getTotalToolsCount,
    fetchServers,
    fetchTools
  } = useMCPStore()

  // Load servers and tools on mount
  useEffect(() => {
    fetchServers()
    fetchTools()
  }, [])

  const activeServers = getActiveServers()
  const totalTools = getTotalToolsCount()
  const hasServers = servers.length > 0

  const handleClick = () => {
    if (onClick) {
      onClick()
    } else {
      navigate({ to: '/connectors' })
    }
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={handleClick}
            className={cn(
              "h-9 w-9 p-0 border transition-all relative",
              hasServers
                ? "bg-blue-500/5 border-blue-500/30 text-blue-700 dark:text-blue-400 hover:bg-blue-500/10 hover:border-blue-500/50"
                : "bg-orange-500/5 border-orange-500/30 text-orange-700 dark:text-orange-400 hover:bg-orange-500/10 hover:border-orange-500/50",
              className
            )}
          >
            <Wrench className={cn(
              "h-3.5 w-3.5",
              hasServers
                ? "text-blue-600 dark:text-blue-400"
                : "text-orange-600 dark:text-orange-400"
            )} />
            {hasServers && activeServers.length > 0 && (
              <Badge
                variant="secondary"
                className="absolute -top-1 -right-1 h-4 min-w-4 px-1 flex items-center justify-center text-[10px] font-semibold bg-blue-600 dark:bg-blue-500 text-white border-0"
              >
                {activeServers.length}
              </Badge>
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <div>
            {hasServers ? (
              <>
                <p className="font-medium">Connected</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {activeServers.length} server{activeServers.length !== 1 ? 's' : ''} • {totalTools} tool{totalTools !== 1 ? 's' : ''}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Click to manage servers
                </p>
              </>
            ) : (
              <>
                <p className="font-medium">No Servers Configured</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Click to add your first server
                </p>
              </>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
