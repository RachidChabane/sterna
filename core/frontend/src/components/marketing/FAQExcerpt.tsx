import { useState } from 'react'
import { ChevronDown } from 'lucide-react'

interface FAQItem {
  question: string
  answer: string
}

const FAQ_DATA: FAQItem[] = [
  {
    question: 'Is there a free plan?',
    answer: 'Yes. Free includes 5 image gens/week, 50 MB knowledge base, and BYOK support.',
  },
  {
    question: "What does 'bring your own key' mean?",
    answer:
      'You can supply your own API key for OpenAI, Anthropic, Google, etc. We route your request and never charge markup.',
  },
  {
    question: 'How does yearly billing work?',
    answer:
      'Yearly billing gives you two months free compared to monthly. You are billed once per year.',
  },
  {
    question: 'Can I switch plans?',
    answer:
      'Yes, upgrade or downgrade anytime. Changes take effect immediately; prorated credits apply.',
  },
  {
    question: 'Is my data private?',
    answer: "Yes. We don't train on your data. Enterprise data is isolated by tenant.",
  },
  {
    question: 'Which models are supported?',
    answer:
      'GPT-4o, Claude 3.5 / 4, Gemini 2, Mistral, Llama, and dozens more via OpenRouter.',
  },
]

interface FAQExcerptProps {
  items?: FAQItem[]
  limit?: number
}

export function FAQExcerpt({ items = FAQ_DATA, limit = 4 }: FAQExcerptProps) {
  const displayed = items.slice(0, limit)

  return (
    <section className="py-16">
      <div className="container mx-auto px-4 max-w-2xl">
        <h2 className="font-display text-3xl font-bold text-center mb-10">Frequently asked questions</h2>
        <div className="space-y-2">
          {displayed.map((item) => (
            <FAQItem key={item.question} item={item} />
          ))}
        </div>
      </div>
    </section>
  )
}

function FAQItem({ item }: { item: FAQItem }) {
  const [open, setOpen] = useState(false)

  return (
    <details
      className="group rounded-lg border border-border overflow-hidden"
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="flex items-center justify-between gap-4 cursor-pointer select-none px-5 py-4 font-medium hover:bg-muted/50 transition-colors list-none">
        {item.question}
        <ChevronDown
          className={`h-4 w-4 flex-shrink-0 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </summary>
      <div className="px-5 pb-4 text-sm text-muted-foreground">{item.answer}</div>
    </details>
  )
}
