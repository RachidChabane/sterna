/**
 * Centralized type badge component and color utilities.
 *
 * Use <TypeBadge type="pdf" /> everywhere — one component, one look.
 */

import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Alias resolution
// ---------------------------------------------------------------------------

const ALIASES: Record<string, string> = {
  md: 'markdown',
  doc: 'docx',
  tsx: 'react',
  jsx: 'react',
  py: 'python',
  txt: 'text',
  xlsx: 'excel',
  xls: 'excel',
}

function normalize(type: string): string {
  const lower = type.toLowerCase()
  return ALIASES[lower] ?? lower
}

// Reverse: long canonical names → short display labels
const DISPLAY_LABELS: Record<string, string> = {
  markdown: 'md',
  python: 'py',
  react: 'tsx',
  text: 'txt',
  excel: 'xlsx',
}

function displayLabel(type: string): string {
  const lower = type.toLowerCase()
  return DISPLAY_LABELS[lower] ?? lower
}

// ---------------------------------------------------------------------------
// Canonical color map
// ---------------------------------------------------------------------------

const COLOR_MAP: Record<string, string> = {
  react: 'cyan',
  html: 'orange',
  svg: 'purple',
  markdown: 'blue',
  mermaid: 'indigo',
  csv: 'emerald',
  ics: 'violet',
  pdf: 'red',
  docx: 'indigo',
  text: 'slate',
  python: 'yellow',
  js: 'amber',
  ts: 'amber',
  json: 'purple',
  excel: 'emerald',
}

// Hash-based fallback palette for unmapped extensions
const HASH_COLORS = [
  'blue',
  'green',
  'purple',
  'orange',
  'pink',
  'cyan',
  'amber',
  'teal',
  'red',
  'indigo',
]

function hashColor(type: string): string {
  let hash = 0
  for (let i = 0; i < type.length; i++) {
    hash = type.charCodeAt(i) + ((hash << 5) - hash)
  }
  return HASH_COLORS[Math.abs(hash) % HASH_COLORS.length]
}

function resolveColor(type: string): string {
  const key = normalize(type)
  return COLOR_MAP[key] ?? hashColor(key)
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Icon text color for a given type.
 *
 * ```tsx
 * <FileIcon className={cn('h-4 w-4', getTypeIconColor(type))} />
 * ```
 */
export function getTypeIconColor(type: string): string {
  const c = resolveColor(type)
  return `text-${c}-500`
}

/**
 * Icon container background for a given type.
 *
 * ```tsx
 * <div className={cn('p-2 rounded-lg', getTypeIconBg(type))}>
 *   <Icon className={cn('h-4 w-4', getTypeIconColor(type))} />
 * </div>
 * ```
 */
export function getTypeIconBg(type: string): string {
  const c = resolveColor(type)
  return `bg-${c}-500/10`
}

// ---------------------------------------------------------------------------
// TypeBadge Component
// ---------------------------------------------------------------------------

interface TypeBadgeProps {
  type: string
  className?: string
}

/**
 * Universal type badge. Same look everywhere.
 *
 * ```tsx
 * <TypeBadge type="pdf" />
 * <TypeBadge type="react" className="absolute top-2 left-2" />
 * ```
 */
export function TypeBadge({ type, className }: TypeBadgeProps) {
  const c = resolveColor(type)
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full text-[10px] px-1.5 py-0.5 font-medium uppercase leading-none',
        `bg-${c}-500/15 text-${c}-600 dark:text-${c}-400`,
        className,
      )}
    >
      {displayLabel(type)}
    </span>
  )
}
