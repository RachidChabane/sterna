/**
 * ProviderGreeting Component
 *
 * Shows a custom greeting based on the model's provider:
 * - Anthropic: Claude icon with elegant serif greeting
 * - Google: Blue greeting, modern style
 * - OpenAI: Simple question prompt
 */

import { useMemo } from 'react'
import { Sparkles } from 'lucide-react'
import { ModelIcon } from './ModelIcon'
import type { Model } from './types'

interface ProviderGreetingProps {
  model: Model | null
  userName?: string
  onModelClick?: () => void
}

// Get time-based greeting in English
function getTimeGreeting(): { text: string; suffix?: string } {
  const hour = new Date().getHours()
  if (hour < 5) {
    return { text: "Can't sleep", suffix: '?' }
  } else if (hour < 12) {
    return { text: 'Good morning' }
  } else if (hour < 18) {
    return { text: 'Good afternoon' }
  } else {
    return { text: 'Good evening' }
  }
}

// Get first name from full name
function getFirstName(fullName?: string): string {
  if (!fullName) return ''
  return fullName.split(' ')[0]
}

// Normalize provider name for comparison
function normalizeProvider(provider?: string): string {
  if (!provider) return ''
  const p = provider.toLowerCase()
  if (p.includes('anthropic') || p.includes('claude')) return 'anthropic'
  if (p.includes('google') || p.includes('gemini')) return 'google'
  if (p.includes('openai') || p.includes('gpt') || p.includes('o1') || p.includes('o3')) return 'openai'
  return p
}

export function ProviderGreeting({ model, userName, onModelClick }: ProviderGreetingProps) {
  const provider = normalizeProvider(model?.provider)
  const firstName = getFirstName(userName)
  const timeGreeting = useMemo(() => getTimeGreeting(), [])

  // Anthropic style - Claude icon with elegant serif greeting
  if (provider === 'anthropic') {
    return (
      <div className="flex flex-col md:flex-row items-center justify-center gap-4">
        {/* Claude icon */}
        {model && (
          <button
            onClick={onModelClick}
            className="cursor-pointer hover:opacity-80 transition-opacity flex-shrink-0"
            title="View model details"
          >
            <ModelIcon
              modelName={model.name}
              modelId={model.model_id}
              provider={model.provider}
              modelIconSlug={model.model_icon_slug}
              modelIconUrl={model.model_icon_url}
              providerIconSlug={model.provider_icon_slug}
              providerIconUrl={model.provider_icon_url}
              size={36}
              showTooltip={false}
            />
          </button>
        )}

        {/* Greeting text - serif font, elegant */}
        <h1 className="text-3xl md:text-4xl font-serif text-foreground/90 tracking-tight text-center">
          {timeGreeting.text}{firstName ? `, ${firstName}` : ''}{timeGreeting.suffix || ''}
        </h1>
      </div>
    )
  }

  // Google style - blue text, modern
  if (provider === 'google') {
    return (
      <div className="flex flex-col items-center justify-center text-center">
        <h1 className="text-4xl font-medium tracking-tight">
          <span className="bg-gradient-to-r from-blue-500 to-blue-600 bg-clip-text text-transparent">
            {timeGreeting.text}{firstName ? `, ${firstName}` : ''}{timeGreeting.suffix || ''}
          </span>
        </h1>
      </div>
    )
  }

  // OpenAI style - simple question prompt
  if (provider === 'openai') {
    return (
      <div className="flex flex-col items-center justify-center text-center">
        <h1 className="text-3xl font-normal text-foreground/90 tracking-tight">
          What are you working on?
        </h1>
      </div>
    )
  }

  // Default fallback - model icon with greeting (variation of Anthropic style)
  return (
    <div className="flex flex-col md:flex-row items-center justify-center gap-4">
      {/* Model icon */}
      {model ? (
        <button
          onClick={onModelClick}
          className="cursor-pointer hover:opacity-80 transition-opacity flex-shrink-0"
          title="View model details"
        >
          <ModelIcon
            modelName={model.name}
            modelId={model.model_id}
            provider={model.provider}
            modelIconSlug={model.model_icon_slug}
            modelIconUrl={model.model_icon_url}
            providerIconSlug={model.provider_icon_slug}
            providerIconUrl={model.provider_icon_url}
            size={36}
            showTooltip={false}
          />
        </button>
      ) : (
        <div className="w-9 h-9 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
          <Sparkles className="h-5 w-5 text-primary" />
        </div>
      )}

      {/* Greeting text - sans-serif, clean */}
      <h1 className="text-3xl md:text-4xl font-medium text-foreground/90 tracking-tight text-center">
        {timeGreeting.text}{firstName ? `, ${firstName}` : ''}{timeGreeting.suffix || ''}
      </h1>
    </div>
  )
}
