import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

interface ProviderSelectProps {
  providers: string[]
  value: string | undefined
  onValueChange: (value: string | undefined) => void
  size?: 'default' | 'sm'
  className?: string
  maxHeight?: string
}

export function ProviderSelect({
  providers,
  value,
  onValueChange,
  size = 'default',
  className,
  maxHeight = '300px',
}: ProviderSelectProps) {
  const handleValueChange = (newValue: string) => {
    onValueChange(newValue === 'all' ? undefined : newValue)
  }

  return (
    <Select value={value || 'all'} onValueChange={handleValueChange}>
      <SelectTrigger className={cn(size === 'sm' && 'h-8 text-xs', className)}>
        <SelectValue placeholder="All providers" />
      </SelectTrigger>
      <SelectContent className={cn('overflow-y-auto')} style={{ maxHeight }}>
        <SelectItem value="all">All providers</SelectItem>
        {providers.map((provider) => (
          <SelectItem key={provider} value={provider}>
            {provider}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
