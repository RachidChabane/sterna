import { DollarSign } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import { PRICING_CONFIG } from '@/lib/pricing-config'

// Price filter constants (in $/1M tokens - matches API data format)
const PRICE_MIN = 0
const PRICE_MAX = 50  // $50 per 1M tokens
const PRICE_TRANSITION = 1  // $1/1M - midpoint for non-linear scaling

const SLIDER_MIN = 0
const SLIDER_MAX = 1
const SLIDER_MID_POINT = 0.5
const SLIDER_STEP = 0.001

// Step sizes for rounding at different price ranges
const STEP_HIGH_PRICE = 1      // $1 steps for prices >= $10
const STEP_MID_PRICE = 0.1     // $0.10 steps for prices >= $1
const STEP_LOW_PRICE = 0.01    // $0.01 steps for prices < $1

// Format thresholds
const FORMAT_THRESHOLD_HIGH = 10
const FORMAT_THRESHOLD_MID = 1

// Helper to round value to appropriate step based on value
const roundToStep = (value: number): number => {
  let step: number
  if (value >= FORMAT_THRESHOLD_HIGH) {
    step = STEP_HIGH_PRICE
  } else if (value >= FORMAT_THRESHOLD_MID) {
    step = STEP_MID_PRICE
  } else {
    step = STEP_LOW_PRICE
  }
  return Math.round(value / step) * step
}

// Convert slider position (0-1) to price value (0-50 $/1M)
// Non-linear: first half covers $0-$1, second half covers $1-$50
const positionToValue = (position: number): number => {
  if (position <= SLIDER_MID_POINT) {
    // Linear from 0 to PRICE_TRANSITION ($1)
    return (position / SLIDER_MID_POINT) * PRICE_TRANSITION
  } else {
    // Linear from PRICE_TRANSITION ($1) to PRICE_MAX ($50)
    const highRange = PRICE_MAX - PRICE_TRANSITION
    return PRICE_TRANSITION + ((position - SLIDER_MID_POINT) / SLIDER_MID_POINT) * highRange
  }
}

// Convert price value (0-50 $/1M) to slider position (0-1)
const valueToPosition = (value: number): number => {
  if (value <= PRICE_TRANSITION) {
    return (value / PRICE_TRANSITION) * SLIDER_MID_POINT
  } else {
    const highRange = PRICE_MAX - PRICE_TRANSITION
    return SLIDER_MID_POINT + ((value - PRICE_TRANSITION) / highRange) * SLIDER_MID_POINT
  }
}

// Helper to format price (value is already in $/1M)
const formatPrice = (value: number): string => {
  if (value === PRICE_MIN) return 'Free'
  if (value >= FORMAT_THRESHOLD_HIGH) return `$${value.toFixed(0)}`
  if (value >= FORMAT_THRESHOLD_MID) return `$${value.toFixed(1)}`
  return `$${value.toFixed(2)}`
}

interface PriceRangeSliderProps {
  mode: 'single' | 'range'
  value?: number | { min: number; max: number }
  onChange: (value: number | { min: number; max: number } | undefined) => void
  label?: string
  className?: string
}

export function PriceRangeSlider({
  mode,
  value,
  onChange,
  label = `Max Price ($/${PRICING_CONFIG.DISPLAY_UNIT_LABEL} tokens)`,
  className = '',
}: PriceRangeSliderProps) {
  if (mode === 'single') {
    const singleValue = typeof value === 'number' ? value : undefined

    return (
      <div className={`space-y-2 ${className}`}>
        {label && <Label className="text-xs font-medium">{label}</Label>}
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <DollarSign className="h-3 w-3 text-muted-foreground flex-shrink-0" />
            <Slider
              value={[valueToPosition(singleValue ?? PRICE_MAX)]}
              onValueChange={([position]: number[]) => {
                const priceValue = positionToValue(position)
                const roundedValue = roundToStep(priceValue)
                onChange(roundedValue >= PRICE_MAX ? undefined : roundedValue)
              }}
              min={SLIDER_MIN}
              max={SLIDER_MAX}
              step={SLIDER_STEP}
              className="flex-1"
            />
          </div>
          <div className="text-xs text-muted-foreground text-right">
            {singleValue === undefined
              ? 'Any price'
              : singleValue === PRICE_MIN
              ? 'Free only'
              : `Max: ${formatPrice(singleValue)}`
            }
          </div>
        </div>
      </div>
    )
  }

  // Range mode
  const rangeValue = typeof value === 'object' && value !== null
    ? value
    : { min: PRICE_MIN, max: PRICE_MAX }

  return (
    <div className={`space-y-2 ${className}`}>
      {label && <Label>{label}</Label>}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <DollarSign className="h-4 w-4 text-muted-foreground" />
          <Slider
            value={[
              valueToPosition(rangeValue.min),
              valueToPosition(rangeValue.max),
            ]}
            onValueChange={([minPos, maxPos]: number[]) => {
              const minValue = positionToValue(minPos)
              const maxValue = positionToValue(maxPos)
              const roundedMin = roundToStep(minValue)
              const roundedMax = roundToStep(maxValue)
              onChange({ min: roundedMin, max: roundedMax })
            }}
            min={SLIDER_MIN}
            max={SLIDER_MAX}
            step={SLIDER_STEP}
            className="flex-1"
          />
        </div>
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>{formatPrice(rangeValue.min)}</span>
          <span>{formatPrice(rangeValue.max)}</span>
        </div>
      </div>
    </div>
  )
}
