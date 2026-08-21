/**
 * CodingProjectCard Component
 *
 * Entry point card for starting coding projects.
 * Matches the app's visual identity with teal accents and animated borders.
 */

import { FolderGit2, ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CodingProjectCardProps {
  onClick: () => void
  className?: string
}

export function CodingProjectCard({ onClick, className }: CodingProjectCardProps) {
  return (
    <>
      <style>{`
        @keyframes codingCardGradient {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }

        .coding-project-card {
          position: relative;
          transition: all 0.3s ease;
        }

        .coding-project-card::before {
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

        .coding-project-card:hover::before {
          opacity: 1;
          background: linear-gradient(135deg,
            hsl(var(--accent-brand) / 0.6),
            rgba(59, 130, 246, 0.5),
            hsl(var(--accent-brand) / 0.6)
          );
          background-size: 200% 200%;
          animation: codingCardGradient 3s ease infinite;
        }

        .coding-project-card:hover {
          box-shadow: 0 0 20px hsl(var(--accent-brand) / 0.15);
        }

        .coding-project-card .arrow-icon {
          transition: transform 0.2s ease;
        }

        .coding-project-card:hover .arrow-icon {
          transform: translateX(3px);
        }
      `}</style>

      <button
        onClick={onClick}
        className={cn(
          "coding-project-card group",
          "w-full max-w-[280px] mx-auto",
          "flex items-center gap-3 p-3",
          "rounded-xl border border-border/40",
          "bg-background/50",
          "text-left cursor-pointer",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:ring-offset-2",
          className
        )}
      >
        {/* Icon */}
        <div className="flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-lg bg-accent-brand/10 group-hover:bg-accent-brand/20 transition-all duration-300">
          <FolderGit2 className="h-5 w-5 text-accent-brand" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <h3 className="font-semibold text-sm group-hover:text-accent-brand transition-colors duration-300">
              Start Coding Project
            </h3>
            <ArrowRight className="arrow-icon h-3.5 w-3.5 text-muted-foreground group-hover:text-accent-brand transition-colors duration-300" />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Clone a GitHub repo
          </p>
        </div>

        {/* Hover indicator */}
        <div className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
          <div className="w-1.5 h-1.5 rounded-full bg-accent-brand" />
        </div>
      </button>
    </>
  )
}
