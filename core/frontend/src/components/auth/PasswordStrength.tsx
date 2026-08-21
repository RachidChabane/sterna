import { useMemo } from 'react'
import { Check, X } from 'lucide-react'
import { Progress } from '@/components/ui/progress'

interface PasswordStrengthProps {
  password: string
}

interface Requirement {
  label: string
  test: (password: string) => boolean
}

const requirements: Requirement[] = [
  {
    label: 'At least 8 characters',
    test: (password) => password.length >= 8,
  },
  {
    label: 'Contains uppercase letter',
    test: (password) => /[A-Z]/.test(password),
  },
  {
    label: 'Contains lowercase letter',
    test: (password) => /[a-z]/.test(password),
  },
  {
    label: 'Contains number',
    test: (password) => /\d/.test(password),
  },
  {
    label: 'Contains special character',
    test: (password) => /[!@#$%^&*(),.?":{}|<>]/.test(password),
  },
]

// Five-step label spectrum collapses to three colours (destructive ->
// muted -> teal) via opacity to stay on existing tokens; see plan §3.13.
function strengthClasses(progress: number) {
  if (progress <= 25) return { text: 'text-destructive', indicator: 'bg-destructive' }
  if (progress <= 50) return { text: 'text-destructive/80', indicator: 'bg-destructive/80' }
  if (progress <= 75) return { text: 'text-muted-foreground', indicator: 'bg-muted-foreground' }
  if (progress < 100) return { text: 'text-accent-brand/80', indicator: 'bg-accent-brand/80' }
  return { text: 'text-accent-brand', indicator: 'bg-accent-brand' }
}

export function PasswordStrength({ password }: PasswordStrengthProps) {
  const { strengthText, strengthColor, indicatorColor, progressValue } = useMemo(() => {
    if (!password) {
      return {
        strengthText: '',
        strengthColor: '',
        indicatorColor: '',
        progressValue: 0,
      }
    }

    const passedRequirements = requirements.filter((req) => req.test(password)).length
    const progress = (passedRequirements / requirements.length) * 100

    let label = ''
    if (progress === 0) label = 'Very Weak'
    else if (progress <= 25) label = 'Weak'
    else if (progress <= 50) label = 'Fair'
    else if (progress <= 75) label = 'Good'
    else label = 'Strong'

    const { text, indicator } = strengthClasses(progress)

    return {
      strengthText: label,
      strengthColor: text,
      indicatorColor: indicator,
      progressValue: progress,
    }
  }, [password])

  if (!password) {
    return null
  }

  return (
    <div className="space-y-3 mt-4">
      <div className="space-y-2">
        <div className="flex justify-between items-center text-sm">
          <span className="text-muted-foreground">Password strength</span>
          <span className={`font-medium ${strengthColor}`}>{strengthText}</span>
        </div>
        <Progress
          value={progressValue}
          className="h-2"
          indicatorClassName={indicatorColor}
        />
      </div>

      <div className="space-y-2">
        <p className="text-sm text-muted-foreground font-medium">Requirements:</p>
        <div className="grid grid-cols-1 gap-1.5">
          {requirements.map((requirement, index) => {
            const passed = requirement.test(password)
            return (
              <div
                key={index}
                className={`flex items-center space-x-2 text-sm ${
                  passed ? 'text-accent-brand' : 'text-muted-foreground'
                }`}
              >
                {passed ? (
                  <Check className="h-4 w-4 flex-shrink-0" />
                ) : (
                  <X className="h-4 w-4 flex-shrink-0" />
                )}
                <span>{requirement.label}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// Helper function to validate password strength (for form validation)
export function isPasswordStrong(password: string): boolean {
  return requirements.filter((req) => req.test(password)).length >= 4
}
