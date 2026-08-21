import * as React from "react"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { cn } from "@/lib/utils"

// Custom TooltipProvider with faster default delay (Radix default is 700ms which is too slow)
// Note: Radix Provider/Root render no DOM element and accept no ref,
// so these are plain function components (not forwardRef).
const TooltipProvider = ({
  delayDuration = 100,
  skipDelayDuration = 300,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Provider>) => (
  <TooltipPrimitive.Provider
    delayDuration={delayDuration}
    skipDelayDuration={skipDelayDuration}
    {...props}
  />
)
TooltipProvider.displayName = "TooltipProvider"

// Custom Tooltip with faster default delay as fallback
const Tooltip = ({
  delayDuration = 100,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Root>) => (
  <TooltipPrimitive.Root delayDuration={delayDuration} {...props} />
)
Tooltip.displayName = "Tooltip"

const TooltipTrigger = TooltipPrimitive.Trigger

const TooltipPortal = TooltipPrimitive.Portal

const TooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, avoidCollisions = true, collisionPadding = 8, ...props }, ref) => {
  // Disable tooltips on mobile (no hover capability)
  if (typeof window !== 'undefined' && window.innerWidth < 768) {
    return null
  }

  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        avoidCollisions={avoidCollisions}
        collisionPadding={collisionPadding}
        className={cn(
          "z-[70] overflow-hidden rounded-md bg-popover border border-border px-3 py-1.5 text-xs text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
          className
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  )
})
TooltipContent.displayName = TooltipPrimitive.Content.displayName

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider, TooltipPortal }
