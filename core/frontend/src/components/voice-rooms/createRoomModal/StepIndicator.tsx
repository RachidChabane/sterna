import { cn } from '@/lib/utils'
import type { ModalStep } from './steps'

interface StepIndicatorProps {
  steps: ModalStep[]
  currentStep: number
  onSelectStep: (step: number) => void
  variant: 'mobile' | 'desktop'
}

/** Step tabs shown above the wizard content, for both the mobile sheet and the desktop dialog. */
export function StepIndicator({ steps, currentStep, onSelectStep, variant }: StepIndicatorProps) {
  const isMobile = variant === 'mobile'

  return (
    <div
      className={cn(
        'flex items-center justify-center border-b shrink-0',
        isMobile ? 'gap-2 py-3' : 'gap-3 py-3 bg-muted/30',
      )}
    >
      {steps.map((step) => {
        const StepIcon = step.icon
        const isActive = currentStep === step.id
        const isCompleted = currentStep > step.id

        return (
          <button
            key={step.id}
            onClick={() => onSelectStep(step.id)}
            className={cn(
              isMobile
                ? 'flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all'
                : 'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              isActive
                ? 'bg-accent-brand/15 text-accent-brand'
                : isCompleted
                  ? isMobile
                    ? 'bg-muted/50 text-foreground'
                    : 'bg-background text-foreground hover:bg-muted/50'
                  : isMobile
                    ? 'text-muted-foreground'
                    : 'text-muted-foreground hover:bg-muted/50',
            )}
          >
            <StepIcon className={isMobile ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
            {step.label}
          </button>
        )
      })}
    </div>
  )
}
