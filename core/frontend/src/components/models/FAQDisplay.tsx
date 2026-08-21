/**
 * FAQDisplay Component
 *
 * Displays FAQ results from Brave Search in an accordion format.
 */

import { useState } from 'react'
import { ChevronDown, HelpCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FAQProps {
  faq: {
    results?: Array<{
      question: string
      answer: string
      url?: string
    }>
  }
}

export function FAQDisplay({ faq }: FAQProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(0)

  if (!faq || !faq.results || faq.results.length === 0) return null

  return (
    <div className="w-full border border-border/40 rounded-lg overflow-hidden bg-background/50 divide-y divide-border/40">
        {faq.results.map((item, index) => (
          <div key={index} className="w-full">
            {/* Question Button */}
            <button
              onClick={() => setExpandedIndex(expandedIndex === index ? null : index)}
              className="w-full flex items-center justify-between gap-3 p-3 text-left hover:bg-muted/50 transition-colors"
            >
              <span
                className="text-sm font-medium flex-1 [&_strong]:font-bold [&_a]:text-accent-brand [&_a]:hover:underline"
                dangerouslySetInnerHTML={{ __html: item.question }}
              />
              <ChevronDown
                className={cn(
                  "h-4 w-4 text-muted-foreground flex-shrink-0 transition-transform",
                  expandedIndex === index && "transform rotate-180"
                )}
              />
            </button>

            {/* Answer */}
            {expandedIndex === index && (
              <div className="px-3 pb-3 space-y-2">
                <p
                  className="text-sm text-foreground/90 leading-relaxed [&_strong]:font-semibold [&_a]:text-accent-brand [&_a]:hover:underline"
                  dangerouslySetInnerHTML={{ __html: item.answer }}
                />
                {item.url && (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-accent-brand hover:underline inline-block"
                  >
                    Source →
                  </a>
                )}
              </div>
            )}
          </div>
        ))}
    </div>
  )
}
