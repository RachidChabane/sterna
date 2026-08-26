import { useState, useCallback } from 'react'
import {
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import { arrayMove, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import type { VoiceSettings } from '@/types/voiceRoom'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import { createDefaultAgent } from './constants'
import type { AgentFormData } from './types'

const MAX_AGENTS = 6

/**
 * Owns the agent list for the create/edit room form: add/remove/edit agents,
 * which ones are expanded, and drag-to-reorder — the "agent roster" concern.
 * Reads recommendedVoices straight from the voice-room store (rather than as a
 * prop) purely to resolve a voice's display name when an agent's voice_id
 * changes, so this hook has no data dependency on useTtsProviderModels.
 */
export function useAgentRoster() {
  const recommendedVoices = useVoiceRoomStore((s) => s.recommendedVoices)
  const [agents, setAgents] = useState<AgentFormData[]>([createDefaultAgent(1)])
  const [expandedAgents, setExpandedAgents] = useState<Set<number>>(new Set())

  const handleAddAgent = () => {
    if (agents.length >= MAX_AGENTS) return
    setAgents([
      ...agents,
      createDefaultAgent(agents.length + 1),
    ])
  }

  const handleRemoveAgent = useCallback((index: number) => {
    setAgents(prevAgents => {
      if (prevAgents.length <= 1) return prevAgents
      const newAgents = prevAgents.filter((_, i) => i !== index)
      // Reorder remaining agents
      return newAgents.map((a, i) => ({ ...a, order: i + 1 }))
    })
  }, [])

  const handleAgentChange = useCallback((index: number, field: keyof AgentFormData, value: string | number | VoiceSettings | undefined) => {
    setAgents(prevAgents => {
      const newAgents = [...prevAgents]
      newAgents[index] = { ...newAgents[index], [field]: value }

      // If voice_id changes, update voice_name
      if (field === 'voice_id' && typeof value === 'string') {
        const voice = recommendedVoices.find((v) => v.voice_id === value)
        if (voice) {
          newAgents[index].voice_name = voice.name
        }
      }

      return newAgents
    })
  }, [recommendedVoices])

  const handleToggleAgentExpand = useCallback((index: number) => {
    setExpandedAgents(prev => {
      const newSet = new Set(prev)
      if (newSet.has(index)) {
        newSet.delete(index)
      } else {
        newSet.add(index)
      }
      return newSet
    })
  }, [])

  // Drag-and-drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px movement before starting drag
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Handle drag end - reorder agents
  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      setAgents((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id)
        const newIndex = items.findIndex((item) => item.id === over.id)

        const reordered = arrayMove(items, oldIndex, newIndex)
        // Update order values
        return reordered.map((item, i) => ({ ...item, order: i + 1 }))
      })

      // Update expanded agents indices after reorder
      setExpandedAgents((prev) => {
        const items = agents
        const oldIndex = items.findIndex((item) => item.id === active.id)
        const newIndex = items.findIndex((item) => item.id === over.id)

        const newSet = new Set<number>()
        prev.forEach((expandedIndex) => {
          if (expandedIndex === oldIndex) {
            newSet.add(newIndex)
          } else if (oldIndex < newIndex) {
            // Item moved down
            if (expandedIndex > oldIndex && expandedIndex <= newIndex) {
              newSet.add(expandedIndex - 1)
            } else {
              newSet.add(expandedIndex)
            }
          } else {
            // Item moved up
            if (expandedIndex >= newIndex && expandedIndex < oldIndex) {
              newSet.add(expandedIndex + 1)
            } else {
              newSet.add(expandedIndex)
            }
          }
        })
        return newSet
      })
    }
  }, [agents])

  return {
    agents,
    setAgents,
    expandedAgents,
    setExpandedAgents,
    handleAddAgent,
    handleRemoveAgent,
    handleAgentChange,
    handleToggleAgentExpand,
    sensors,
    handleDragEnd,
  }
}
