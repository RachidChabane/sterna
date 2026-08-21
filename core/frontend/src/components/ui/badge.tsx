import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80 hover:text-primary-foreground shadow-sm",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80 hover:text-secondary-foreground shadow-sm",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80 hover:text-destructive-foreground shadow-sm",
        outline: "text-foreground",
        success:
          "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 hover:text-emerald-800 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 dark:hover:bg-emerald-900/50",
        warning:
          "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100 hover:text-amber-800 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-400 dark:hover:bg-amber-900/50",
        info:
          "border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 hover:text-violet-800 dark:border-violet-700 dark:bg-violet-900/30 dark:text-violet-400 dark:hover:bg-violet-900/50",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }