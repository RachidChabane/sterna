import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks/useTheme'
import { cn } from '@/lib/utils'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      className={cn(
        "relative h-9 w-9 rounded-lg",
        "hover:bg-secondary transition-colors"
      )}
      aria-label="Toggle theme"
    >
      <Sun className={cn(
        "h-5 w-5 transition-all",
        theme === 'dark' ? 'rotate-0 scale-100' : 'rotate-90 scale-0'
      )} />
      <Moon className={cn(
        "absolute h-5 w-5 transition-all",
        theme === 'light' ? 'rotate-0 scale-100' : 'rotate-90 scale-0'
      )} />
      <span className="sr-only">Toggle theme</span>
    </Button>
  )
}
