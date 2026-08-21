/**
 * SpeakerIndicator - Minimal current speaker display
 *
 * Shows who is currently active in the conversation
 * with a subtle, unobtrusive design.
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { ModelIcon } from '@/components/models/ModelIcon'
import { User } from 'lucide-react'
import useModelStore from '@/store/modelStore'
import type { VoiceAgent } from '@/types/voiceRoom'

interface SpeakerIndicatorProps {
  agents: VoiceAgent[]
  currentSpeaker: string | null | undefined
  isListening: boolean
  isSpeaking: boolean
  isProcessing: boolean
  className?: string
}

export function SpeakerIndicator({
  agents,
  currentSpeaker,
  isListening,
  isSpeaking,
  isProcessing,
  className,
}: SpeakerIndicatorProps) {
  const { allModels } = useModelStore()

  const speakerInfo = useMemo(() => {
    if (isListening) {
      return { name: 'You', isUser: true, modelId: null }
    }

    if (isSpeaking || isProcessing) {
      const agent = agents.find(a => a.id === currentSpeaker)
      if (agent) {
        return { name: agent.display_name, isUser: false, modelId: agent.model_id }
      }
    }

    return null
  }, [agents, currentSpeaker, isListening, isSpeaking, isProcessing])

  if (!speakerInfo) {
    return (
      <div className={cn('flex items-center justify-center gap-2 h-8', className)}>
        <span className="text-white/20 text-sm">Ready to listen</span>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex items-center justify-center gap-3 transition-all duration-300',
        className
      )}
    >
      {/* Speaker icon */}
      <div
        className={cn(
          'h-7 w-7 rounded-full flex items-center justify-center',
          'bg-white/5 backdrop-blur-sm',
          'ring-1',
          speakerInfo.isUser
            ? 'ring-green-500/30'
            : isSpeaking
            ? 'ring-blue-500/30'
            : 'ring-purple-500/30'
        )}
      >
        {speakerInfo.isUser ? (
          <User className="h-3.5 w-3.5 text-green-400/80" />
        ) : (() => {
          const model = allModels.find((m) => m.model_id === speakerInfo.modelId)
          return (
            <ModelIcon
              modelName={model?.name || speakerInfo.name}
              modelId={speakerInfo.modelId || ''}
              provider={model?.provider || ''}
              modelIconSlug={model?.model_icon_slug}
              modelIconUrl={model?.model_icon_url}
              providerIconSlug={model?.provider_icon_slug}
              providerIconUrl={model?.provider_icon_url}
              className="h-4 w-4"
            />
          )
        })()}
      </div>

      {/* Speaker name */}
      <span
        className={cn(
          'text-sm font-medium',
          speakerInfo.isUser
            ? 'text-green-400/80'
            : isSpeaking
            ? 'text-blue-400/80'
            : 'text-purple-400/80'
        )}
      >
        {speakerInfo.name}
      </span>

      {/* Status indicator */}
      <span className="text-white/30 text-sm">
        {isListening ? 'listening' : isProcessing ? 'thinking' : 'speaking'}
      </span>
    </div>
  )
}
