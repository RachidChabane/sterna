/**
 * Suggested Questions Component
 *
 * Displays a grid of suggested questions for model comparison.
 * Features a professional, elegant design with dark cards and teal accents.
 * Questions are organized by category in tabs for better UX.
 * Redesigned with compact layout and animated borders matching the input style.
 */

import { useState } from 'react'
import { SUGGESTED_QUESTIONS, QUESTION_CATEGORIES, type QuestionCategory } from './constants/suggestedQuestions'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

interface SuggestedQuestionsProps {
  onSuggestionClick: (prompt: string) => void
}

export function SuggestedQuestions({ onSuggestionClick }: SuggestedQuestionsProps) {
  const [activeCategory, setActiveCategory] = useState<QuestionCategory>('code')

  return (
    <>
      <style>{`
        @keyframes gradientShift {
          0% {
            background-position: 0% 50%;
          }
          50% {
            background-position: 100% 50%;
          }
          100% {
            background-position: 0% 50%;
          }
        }

        .suggestion-card {
          position: relative;
          transition: background-color 0.3s ease;
        }

        .suggestion-card::before {
          content: '';
          position: absolute;
          inset: -1px;
          border-radius: inherit;
          padding: 1px;
          background: linear-gradient(135deg, transparent, transparent);
          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          -webkit-mask-composite: xor;
          mask-composite: exclude;
          opacity: 0;
          transition: opacity 0.3s ease;
          pointer-events: none;
        }

        .suggestion-card:hover::before {
          opacity: 1;
          background: linear-gradient(135deg,
            rgba(59, 130, 246, 0.5),
            rgba(61, 92, 228, 0.5),
            rgba(59, 130, 246, 0.5)
          );
          background-size: 200% 200%;
          animation: gradientShift 3s ease infinite;
        }

        /* Light mode: better contrast */
        .light .suggestion-card {
          background: hsl(var(--card) / 0.8);
        }
      `}</style>
      <div className="flex flex-col items-center justify-center h-full px-6 py-4">
        {/* Header - More compact */}
        <div className="text-center mb-4">
          <h3 className="text-lg font-semibold mb-1">Get started with these questions</h3>
          <p className="text-xs text-muted-foreground max-w-2xl">
            Select a suggested prompt to test the capabilities of your model
          </p>
        </div>

        {/* Categorized Tabs */}
        <Tabs
          value={activeCategory}
          onValueChange={(value) => setActiveCategory(value as QuestionCategory)}
          className="w-full max-w-4xl"
        >
          {/* Category Tabs - More compact */}
          <TabsList className="grid w-full grid-cols-3 mb-4 h-9">
            {QUESTION_CATEGORIES.map((category) => {
              const questionsCount = SUGGESTED_QUESTIONS.filter(
                (q) => q.category === category.id
              ).length
              return (
                <TabsTrigger
                  key={category.id}
                  value={category.id}
                  className="text-xs data-[state=active]:bg-accent-brand/10 data-[state=active]:text-accent-brand"
                >
                  {category.label}
                  <span className="ml-1 text-[10px] opacity-60">({questionsCount})</span>
                </TabsTrigger>
              )
            })}
          </TabsList>

          {/* Tab Content for each category */}
          {QUESTION_CATEGORIES.map((category) => {
            const categoryQuestions = SUGGESTED_QUESTIONS.filter(
              (q) => q.category === category.id
            )

            return (
              <TabsContent key={category.id} value={category.id} className="mt-0">
                {/* Category Description - More compact */}
                <p className="text-center text-xs text-muted-foreground mb-3">
                  {category.description}
                </p>

                {/* Question Grid - Compact 2x2 layout */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {categoryQuestions.map((question, index) => {
                    const Icon = question.icon
                    return (
                      <button
                        key={index}
                        onClick={() => onSuggestionClick(question.prompt)}
                        className="suggestion-card group relative flex items-center gap-3 p-3 rounded-xl
                                 bg-background/50 border border-border/40
                                 text-left
                                 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:ring-offset-2"
                      >
                        {/* Icon - More compact */}
                        <div className="flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-lg
                                      bg-accent-brand/10 group-hover:bg-accent-brand/20
                                      transition-all duration-300">
                          <Icon className="h-4 w-4 text-accent-brand" />
                        </div>

                        {/* Content - Side by side with icon */}
                        <div className="flex-1 min-w-0">
                          <h4 className="font-semibold text-sm mb-0.5 group-hover:text-accent-brand transition-colors duration-300">
                            {question.title}
                          </h4>
                          <p className="text-xs text-muted-foreground line-clamp-1">
                            {question.description}
                          </p>
                        </div>

                        {/* Hover indicator - Smaller */}
                        <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                          <div className="w-1.5 h-1.5 rounded-full bg-accent-brand" />
                        </div>
                      </button>
                    )
                  })}
                </div>
              </TabsContent>
            )
          })}
        </Tabs>

        {/* Footer hint - More compact */}
        <p className="text-[10px] text-muted-foreground/50 mt-3">
          Click on any question to fill the input and start chatting
        </p>
      </div>
    </>
  )
}
