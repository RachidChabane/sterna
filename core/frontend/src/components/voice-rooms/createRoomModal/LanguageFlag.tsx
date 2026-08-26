import { Globe } from 'lucide-react'
import { CircleFlag } from 'react-circle-flags'

/** Flag component with a globe fallback for unknown/empty country codes. */
export function LanguageFlag({ countryCode, size = 16 }: { countryCode: string; size?: number }) {
  if (!countryCode) {
    return <Globe className="text-muted-foreground flex-shrink-0" style={{ width: size, height: size }} />
  }
  return (
    <span className="flex-shrink-0 inline-flex" style={{ width: size, height: size }}>
      <CircleFlag countryCode={countryCode.toLowerCase()} width={size} height={size} />
    </span>
  )
}
