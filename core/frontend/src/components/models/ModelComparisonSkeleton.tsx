import { Skeleton } from '@/components/ui/skeleton'

/**
 * Placeholder shown when the active conversation group is selected but its
 * chats have not loaded yet, matching ImmersiveChatView's structure
 * (max-w-[52rem] centered content) to avoid a layout jump once real content
 * arrives.
 */
export function ModelComparisonSkeleton() {
  return (
    <div className="h-full flex flex-col bg-background relative">
      {/* Header skeleton - matches ImmersiveChatView header */}
      <div className="sticky top-0 z-10 flex items-center justify-between gap-2 px-3 py-2 border-b bg-background/95 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-8 rounded-lg" />
          <Skeleton className="hidden md:block h-5 w-32" />
        </div>
        <div className="flex items-center gap-1">
          <Skeleton className="h-8 w-8 rounded-md" />
          <Skeleton className="h-8 w-8 rounded-md" />
        </div>
      </div>

      {/* Messages area skeleton - centered with max-w-[52rem] like ImmersiveChatView */}
      <div className="flex-1 overflow-y-auto pb-44">
        <div className="max-w-[52rem] mx-auto px-6 py-8 space-y-6">
          {/* User message skeleton */}
          <div className="flex justify-end">
            <div className="max-w-[85%] md:max-w-[75%]">
              <div className="bg-primary/10 rounded-2xl rounded-tr-sm px-4 py-3 space-y-2">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-4 w-32" />
              </div>
            </div>
          </div>

          {/* Assistant message skeleton */}
          <div className="flex justify-start gap-3">
            <Skeleton className="h-8 w-8 rounded-full flex-shrink-0 mt-1" />
            <div className="max-w-[85%] md:max-w-[75%]">
              <div className="space-y-2">
                <Skeleton className="h-4 w-64" />
                <Skeleton className="h-4 w-56" />
                <Skeleton className="h-4 w-40" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Input area skeleton - floating at bottom like ImmersiveChatView */}
      <div className="absolute bottom-0 left-0 right-0 pointer-events-none">
        <div className="bg-background pb-3 md:pb-5 px-4 md:px-6 pointer-events-auto">
          <div className="max-w-[52rem] mx-auto">
            <div className="rounded-2xl bg-card/98 backdrop-blur-md border border-border/40 shadow-lg p-3">
              <div className="flex items-center gap-2">
                <Skeleton className="h-10 flex-1 rounded-xl" />
                <Skeleton className="h-10 w-10 rounded-xl" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
