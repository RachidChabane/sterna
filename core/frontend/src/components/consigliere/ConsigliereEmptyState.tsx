/**
 * Empty state component for Consigliere chat with message suggestions
 */

import { Button } from '@/components/ui/button'
import { Sparkles, Target, DollarSign, Zap, BarChart } from 'lucide-react'

interface ConsigliereEmptyStateProps {
  onSuggestionClick: (message: string) => void
}

export function ConsigliereEmptyState({ onSuggestionClick }: ConsigliereEmptyStateProps) {
  const suggestions = [
    {
      icon: Target,
      text: "Which model is best suited for my use case?",
    },
    {
      icon: DollarSign,
      text: "How can I reduce my costs?",
    },
    {
      icon: Zap,
      text: "Which models offer the fastest response times?",
    },
    {
      icon: BarChart,
      text: "Compare current conversation performance",
    },
  ]

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 py-12">
      <div className="relative mb-4">
        <Sparkles className="h-12 w-12 text-primary" />
      </div>
      <h3 className="text-xl font-semibold mb-2">
        AI Model Advisor
      </h3>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        I can help you select the optimal model for your needs, analyze costs, and provide performance insights.
      </p>

      <div className="grid grid-cols-1 gap-2 w-full max-w-md">
        {suggestions.map((suggestion, index) => {
          const Icon = suggestion.icon
          return (
            <Button
              key={index}
              variant="outline"
              className="justify-start text-left h-auto py-3 px-4 hover:bg-primary/5 hover:border-primary/50"
              onClick={() => onSuggestionClick(suggestion.text)}
            >
              <Icon className="h-4 w-4 mr-2 text-muted-foreground flex-shrink-0" />
              <span className="text-sm">{suggestion.text}</span>
            </Button>
          )
        })}
      </div>
    </div>
  )
}
