import { useEffect } from 'react'
import { useUsageQuotaStore } from '@/store/usageQuotaStore'
import { Loader2, AlertCircle, RefreshCw } from 'lucide-react'

function UsageProgressBar({ percentage }: { percentage: number }) {
  return (
    <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
      <div
        className="h-full bg-brand-500 rounded-full transition-all duration-300"
        style={{ width: `${Math.min(percentage, 100)}%` }}
      />
    </div>
  )
}

function formatSessionReset(windowEnd: string): string {
  // Empty string means no active window
  if (!windowEnd) return 'No active window'

  const end = new Date(windowEnd)
  const now = new Date()
  const diffMs = end.getTime() - now.getTime()

  if (diffMs <= 0) return 'Resetting...'

  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60))

  if (diffHours > 0) {
    return `Resets in ${diffHours}h ${diffMinutes}m`
  }

  return `Resets in ${diffMinutes}m`
}

function formatWeeklyReset(windowEnd: string, short = false): string {
  // Empty string means no active window
  if (!windowEnd) return 'No active window'

  const end = new Date(windowEnd)
  const now = new Date()

  if (end.getTime() <= now.getTime()) return 'Resetting...'

  // Use English day names for consistency with the rest of the UI
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
  const fullDay = days[end.getDay()]
  const day = short ? fullDay.slice(0, 3) + '.' : fullDay
  const time = end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })

  return `Resets ${day} ${time}`
}

function formatLastUpdated(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function SessionUsageRow() {
  const { quota } = useUsageQuotaStore()

  if (!quota) return null

  const sessionLimit = parseFloat(quota.session.limit_usd)
  const sessionUsed = parseFloat(quota.session.used_usd)
  const percentage = sessionLimit > 0 ? (sessionUsed / sessionLimit) * 100 : 0
  const resetText = formatSessionReset(quota.session.window_end)

  return (
    <div className="py-3 border-b border-border">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-foreground">Session</div>
          <div className="text-xs text-muted-foreground">{resetText}</div>
        </div>
        <div className="flex items-center gap-3 flex-1 max-w-[60%] ml-4">
          <UsageProgressBar percentage={percentage} />
          <span className="text-sm text-muted-foreground tabular-nums w-20 text-right">
            {percentage.toFixed(0)}% used
          </span>
        </div>
      </div>
    </div>
  )
}

function WeeklyUsageRow() {
  const { quota } = useUsageQuotaStore()

  if (!quota) return null

  const usedUsd = parseFloat(quota.weekly.used_usd)
  const limitUsd = parseFloat(quota.weekly.limit_usd)
  const percentage = limitUsd > 0 ? (usedUsd / limitUsd) * 100 : 0
  const resetTextFull = formatWeeklyReset(quota.weekly.window_end, false)
  const resetTextShort = formatWeeklyReset(quota.weekly.window_end, true)

  return (
    <div className="py-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-foreground">Weekly</div>
          <div className="text-xs text-muted-foreground">
            <span className="hidden sm:inline">{resetTextFull}</span>
            <span className="sm:hidden">{resetTextShort}</span>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-1 max-w-[60%] ml-4">
          <UsageProgressBar percentage={percentage} />
          <span className="text-sm text-muted-foreground tabular-nums w-20 text-right">
            {percentage.toFixed(0)}% used
          </span>
        </div>
      </div>
    </div>
  )
}

export function UsageQuotaSettings() {
  const { quota, isLoadingQuota, quotaError, fetchQuota } = useUsageQuotaStore()

  // Fetch data on mount
  useEffect(() => {
    fetchQuota()
  }, [fetchQuota])

  // Track last updated time
  const lastUpdated = new Date()

  if (isLoadingQuota && !quota) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (quotaError) {
    return (
      <div className="flex items-center gap-2 text-destructive py-8">
        <AlertCircle className="h-4 w-4" />
        <span className="text-sm">{quotaError}</span>
      </div>
    )
  }

  if (!quota) {
    return (
      <div className="text-sm text-muted-foreground py-8 text-center">
        No usage data available
      </div>
    )
  }

  return (
    <div>
      {/* Plan name at top */}
      <div className="pb-3 border-b border-border">
        <div className="text-sm font-semibold text-foreground">{quota.plan_display_name}</div>
      </div>

      {/* Usage rows */}
      <SessionUsageRow />
      <WeeklyUsageRow />

      {/* Last updated with refresh */}
      <div className="pt-3 mt-2 border-t border-border flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          Last updated: {formatLastUpdated(lastUpdated)}
        </span>
        <button
          onClick={() => fetchQuota()}
          disabled={isLoadingQuota}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-3 w-3 ${isLoadingQuota ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>
    </div>
  )
}

export default UsageQuotaSettings
