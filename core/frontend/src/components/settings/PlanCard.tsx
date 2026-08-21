import { useEffect, useState } from 'react'
import { Loader2, AlertCircle, Infinity as InfinityIcon } from 'lucide-react'
import { subscriptionApi } from '@/api/subscription'
import type {
  PerFeatureLimits,
  PerFeatureUsage,
  SubscriptionFeatures,
  SubscriptionPlan,
  SubscriptionUsage,
} from '@/api/types'

type FeatureKey = keyof PerFeatureLimits

const FEATURE_LABELS: Record<FeatureKey, { label: string; flagKey: keyof SubscriptionFeatures }> = {
  voice_room:    { label: 'Voice rooms',          flagKey: 'voice_rooms' },
  code_session:  { label: 'Code sessions',        flagKey: 'code_sessions' },
  image_gen:     { label: 'Image generation',     flagKey: 'image_gen' },
  video_gen:     { label: 'Video generation (s)', flagKey: 'video_gen' },
  mcp:           { label: 'MCP invocations',      flagKey: 'mcp' },
  kb_docs:       { label: 'Knowledge base docs',  flagKey: 'knowledge_base' },
  kb_storage_mb: { label: 'KB storage (MB)',      flagKey: 'knowledge_base' },
}

const FEATURE_ORDER: FeatureKey[] = [
  'voice_room',
  'code_session',
  'image_gen',
  'video_gen',
  'mcp',
  'kb_docs',
  'kb_storage_mb',
]

function FeatureRow({
  featureKey,
  usage,
  isEnabled,
}: {
  featureKey: FeatureKey
  usage: PerFeatureUsage
  isEnabled: boolean
}) {
  const meta = FEATURE_LABELS[featureKey]

  if (!isEnabled) {
    return (
      <div className="py-2 flex items-center justify-between">
        <span className="text-sm">{meta.label}</span>
        <span className="text-xs text-muted-foreground italic">Not in your plan</span>
      </div>
    )
  }

  if (usage.limit === null) {
    return (
      <div className="py-2 flex items-center justify-between">
        <span className="text-sm">{meta.label}</span>
        <span className="text-xs text-muted-foreground flex items-center gap-1">
          <InfinityIcon className="h-3 w-3" /> Unlimited
        </span>
      </div>
    )
  }

  // `used === null` means the backend has the LIMIT but no reliable count
  // yet (task-10 ATTRIBUTABLE_USAGE_KEYS). Render the limit alone instead
  // of a misleading "0 / N" bar.
  if (usage.used === null) {
    return (
      <div className="py-2 flex items-center justify-between">
        <span className="text-sm">{meta.label}</span>
        <span
          className="text-xs tabular-nums text-muted-foreground"
          title="Per-feature usage tracking is coming in task 10"
        >
          — / {usage.limit}
        </span>
      </div>
    )
  }

  const pct = usage.limit > 0 ? (usage.used / usage.limit) * 100 : 0
  return (
    <div className="py-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm">{meta.label}</span>
        <span className="text-xs tabular-nums text-muted-foreground">
          {usage.used} / {usage.limit}
        </span>
      </div>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-brand-500 transition-all duration-300"
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}

export function PlanCard() {
  const [plan, setPlan] = useState<SubscriptionPlan | null>(null)
  const [usage, setUsage] = useState<SubscriptionUsage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([subscriptionApi.getPlan(), subscriptionApi.getUsage()])
      .then(([p, u]) => {
        if (cancelled) return
        setPlan(p)
        setUsage(u)
        setLoading(false)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e?.message ?? 'Failed to load plan')
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (loading) {
    return (
      <div className="py-6 flex justify-center">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    )
  }
  if (error) {
    return (
      <div className="py-6 flex items-center gap-2 text-destructive">
        <AlertCircle className="h-4 w-4" />
        {error}
      </div>
    )
  }
  if (!plan || !usage) return null

  return (
    <div className="border border-border rounded-lg p-4 mb-4">
      <div className="flex items-baseline justify-between mb-3 pb-3 border-b border-border">
        <div>
          <div className="text-base font-semibold">{plan.display_name}</div>
          <div className="text-xs text-muted-foreground">{plan.description}</div>
        </div>
      </div>
      <div className="space-y-1">
        {FEATURE_ORDER.map((k) => {
          const flagKey = FEATURE_LABELS[k].flagKey
          return (
            <FeatureRow
              key={k}
              featureKey={k}
              usage={usage.per_feature[k]}
              isEnabled={Boolean(plan.features[flagKey])}
            />
          )
        })}
      </div>
    </div>
  )
}

export default PlanCard
