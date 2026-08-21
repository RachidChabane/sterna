import { HelpCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useHelpDrawerStore } from '@/store/helpDrawerStore'

export function HelpDrawerTrigger() {
  const open = useHelpDrawerStore((s) => s.open)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-full"
          onClick={() => open('faq')}
          aria-label="Open help"
        >
          <HelpCircle className="h-5 w-5 text-muted-foreground" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>Help & Support</TooltipContent>
    </Tooltip>
  )
}
