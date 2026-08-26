import { Button } from '@/components/ui/button'
import {
  DndContext,
  closestCenter,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { Plus } from 'lucide-react'
import { AgentForm } from './AgentForm'
import type { AgentFormData, VoiceSettingsFormState } from './types'
import type { Model } from '@/components/models/types'
import type { VoiceInfo, VoiceSettings } from '@/types/voiceRoom'

type Sensors = ReturnType<typeof useSensors>

interface DesktopAgentsStepProps {
  agents: AgentFormData[]
  handleAddAgent: () => void
  handleRemoveAgent: (index: number) => void
  handleAgentChange: (index: number, field: keyof AgentFormData, value: string | number | VoiceSettings | undefined) => void
  expandedAgents: Set<number>
  handleToggleAgentExpand: (index: number) => void
  sensors: Sensors
  handleDragEnd: (event: DragEndEvent) => void
  voiceRoomModels: Model[]
  recommendedVoices: VoiceInfo[]
  selectedProvider: string
  voiceSettings: VoiceSettingsFormState
  language: string
}

/** Step 2 (Agents) content for the desktop dialog: full agent cards with drag-to-reorder. */
export function DesktopAgentsStep({
  agents,
  handleAddAgent,
  handleRemoveAgent,
  handleAgentChange,
  expandedAgents,
  handleToggleAgentExpand,
  sensors,
  handleDragEnd,
  voiceRoomModels,
  recommendedVoices,
  selectedProvider,
  voiceSettings,
  language,
}: DesktopAgentsStepProps) {
  return (
    <div className="space-y-4">
      {/* Agent count header */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{agents.length} of 6 agents</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleAddAgent}
          disabled={agents.length >= 6}
          className="h-8 gap-1"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Agent
        </Button>
      </div>

      {/* Agent cards with drag-drop */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={agents.map(a => a.id)}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-2">
            {agents.map((agent, index) => (
              <AgentForm
                key={agent.id}
                agent={agent}
                index={index}
                agentCount={agents.length}
                models={voiceRoomModels}
                recommendedVoices={recommendedVoices}
                onAgentChange={handleAgentChange}
                onRemoveAgent={handleRemoveAgent}
                isExpanded={expandedAgents.has(index)}
                onToggleExpand={() => handleToggleAgentExpand(index)}
                selectedProvider={selectedProvider}
                voiceSettings={voiceSettings}
                language={language}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  )
}
