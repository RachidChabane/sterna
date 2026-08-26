/**
 * Pure parsing/formatting helpers shared by two or more tool renderers.
 * Renderer-specific helpers stay colocated with their renderer instead.
 */

// Parse nested JSON/object structures
export const deepParse = (val: any): any => {
  if (typeof val === 'string') {
    try { return deepParse(JSON.parse(val)) } catch { return val }
  }
  return val
}

// Helper to try parsing a value as JSON if it's a string
export const tryParseJSON = (value: any): any => {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

// Sanitize and format output for display
// Handles escaped characters, truncates long output, and ensures proper line breaks
export const sanitizeOutput = (output: string | undefined | null, maxLength = 10000): string => {
  if (!output) return ''

  let sanitized = String(output)

  // Unescape common escape sequences that might be double-escaped
  sanitized = sanitized
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '\r')
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'")

  // Truncate if too long
  if (sanitized.length > maxLength) {
    sanitized = sanitized.slice(0, maxLength) + '\n\n... (output truncated)'
  }

  return sanitized
}

export interface DiffLine {
  type: 'header' | 'hunk' | 'context' | 'added' | 'removed'
  content: string
  oldLineNum?: number
  newLineNum?: number
}

// Parse a unified diff into structured lines with line numbers
export const parseDiffLines = (diffText: string): DiffLine[] => {
  const lines = diffText.split('\n')
  const parsedLines: DiffLine[] = []

  let oldLine = 0
  let newLine = 0

  for (const line of lines) {
    if (line.startsWith('---') || line.startsWith('+++')) {
      parsedLines.push({ type: 'header', content: line })
    } else if (line.startsWith('@@')) {
      // Parse hunk header like @@ -113,19 +113,4 @@
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
      if (match) {
        oldLine = parseInt(match[1], 10)
        newLine = parseInt(match[2], 10)
      }
      parsedLines.push({ type: 'hunk', content: line })
    } else if (line.startsWith('-')) {
      parsedLines.push({ type: 'removed', content: line, oldLineNum: oldLine })
      oldLine++
    } else if (line.startsWith('+')) {
      parsedLines.push({ type: 'added', content: line, newLineNum: newLine })
      newLine++
    } else {
      // Context line (starts with space or empty)
      parsedLines.push({ type: 'context', content: line, oldLineNum: oldLine, newLineNum: newLine })
      oldLine++
      newLine++
    }
  }

  return parsedLines
}
