import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Mic, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ModelIcon } from '@/components/models/ModelIcon'
import useModelStore from '@/store/modelStore'
import type { VoiceRoom } from '@/types/voiceRoom'
import { formatDistanceToNow } from 'date-fns'

interface RoomListProps {
  rooms: VoiceRoom[]
  selectedRoom: VoiceRoom | null
  onSelect: (room: VoiceRoom) => void
  onStartSession: (room: VoiceRoom) => void
  onEditRoom: (room: VoiceRoom) => void
  onDeleteRoom: (room: VoiceRoom) => void
  onViewModelDetails?: (modelId: string) => void
}

export function RoomList({
  rooms,
  selectedRoom,
  onSelect,
  onStartSession,
  onEditRoom,
  onDeleteRoom,
  onViewModelDetails,
}: RoomListProps) {
  const { allModels } = useModelStore()

  // Helper to find model info by model_id
  const getModelInfo = (modelId: string) => {
    return allModels.find(m => m.model_id === modelId)
  }

  return (
    <TooltipProvider>
      <div className="space-y-1">
        {rooms.map((room) => {
          const agentCount = room.agents?.length ?? 0
          const isSelected = selectedRoom?.id === room.id

          return (
            <div
              key={room.id}
              className={cn(
                "group relative rounded-lg p-2.5 pr-9 cursor-pointer transition-all",
                "hover:bg-secondary/80 hover:ring-1 hover:ring-border",
                isSelected
                  ? "bg-secondary ring-1 ring-accent-brand/30"
                  : ""
              )}
              onClick={() => onSelect(room)}
            >
              {/* Top row: Room name + Date */}
              <div className="flex items-start justify-between gap-2 mb-1">
                <h3 className={cn(
                  "text-[13px] font-medium truncate flex-1",
                  isSelected ? "text-accent-brand" : "text-foreground/90"
                )}>
                  {room.name}
                </h3>
                <span className="text-[10px] text-muted-foreground/60 flex-shrink-0">
                  {formatDistanceToNow(new Date(room.updated_at), { addSuffix: false })}
                </span>
              </div>

              {/* Bottom row: Agent icons + names */}
              {agentCount > 0 && (
                <div className="flex items-center gap-2">
                  {/* Stacked model icons */}
                  <div className="flex items-center flex-shrink-0">
                    {room.agents?.slice(0, 3).map((agent, index) => {
                      const model = getModelInfo(agent.model_id)
                      return (
                        <TooltipProvider key={agent.id}>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <button
                                className="relative flex-shrink-0 hover:z-10 transition-transform hover:scale-110 cursor-pointer"
                                style={{ marginLeft: index > 0 ? '-3px' : '0' }}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  onViewModelDetails?.(agent.model_id)
                                }}
                              >
                                <ModelIcon
                                  modelName={model?.name || agent.model_id}
                                  modelId={agent.model_id}
                                  provider={model?.provider || ''}
                                  modelIconSlug={model?.model_icon_slug}
                                  modelIconUrl={model?.model_icon_url}
                                  providerIconSlug={model?.provider_icon_slug}
                                  providerIconUrl={model?.provider_icon_url}
                                  size={16}
                                  showTooltip={false}
                                />
                              </button>
                            </TooltipTrigger>
                            <TooltipContent side="bottom" className="text-xs">
                              {agent.display_name}
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )
                    })}
                    {agentCount > 3 && (
                      <span className="text-[10px] text-muted-foreground/60 ml-1">+{agentCount - 3}</span>
                    )}
                  </div>

                  {/* Agent names */}
                  <div className="flex items-center gap-1 flex-wrap min-w-0 flex-1">
                    {room.agents?.slice(0, 2).map((agent, i) => (
                      <span
                        key={agent.id}
                        className="text-[11px] text-muted-foreground truncate max-w-[80px]"
                      >
                        {agent.display_name}{i < Math.min(agentCount, 2) - 1 && ','}
                      </span>
                    ))}
                    {agentCount > 2 && (
                      <span className="text-[10px] text-muted-foreground/60">
                        +{agentCount - 2}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Actions Dropdown - absolute positioned */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    className={cn(
                      "absolute top-2 right-1.5 h-6 w-6 rounded-full flex items-center justify-center",
                      "hover:bg-muted-foreground/10 transition-opacity",
                      isSelected ? "opacity-100" : "opacity-100 md:opacity-0 md:group-hover:opacity-100"
                    )}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-36" onClick={(e) => e.stopPropagation()}>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      onStartSession(room)
                    }}
                  >
                    <Mic className="h-3.5 w-3.5 mr-2" />
                    Start Session
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      onEditRoom(room)
                    }}
                  >
                    <Pencil className="h-3.5 w-3.5 mr-2" />
                    Edit Room
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      onDeleteRoom(room)
                    }}
                    className="text-destructive focus:text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-2" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )
        })}
      </div>
    </TooltipProvider>
  )
}
