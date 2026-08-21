/**
 * Lightweight CSV parser with basic delimiter detection.
 * - Supports commas, semicolons, and tabs
 * - Handles quoted fields and escaped quotes ("")
 * - Preserves empty cells
 * - Stops after maxRows to keep previews fast
 */

export type CSVDelimiter = ',' | ';' | '\t'

function stripBOM(text: string): string {
  if (text.charCodeAt(0) === 0xfeff) return text.slice(1)
  return text
}

function countDelims(line: string, delim: CSVDelimiter): number {
  let count = 0
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        i++ // skip escaped quote
      } else {
        inQuotes = !inQuotes
      }
    } else if (!inQuotes && ch === delim) {
      count++
    }
  }
  return count
}

export function detectDelimiter(text: string): CSVDelimiter {
  const sample = stripBOM(text).split(/\r?\n/).slice(0, 10)
  const candidates: CSVDelimiter[] = [',', ';', '\t']
  let best: CSVDelimiter = ','
  let bestScore = -1

  for (const delim of candidates) {
    let counts: number[] = []
    for (const line of sample) {
      if (!line) continue
      counts.push(countDelims(line, delim))
    }
    if (counts.length === 0) continue
    // score: higher mean and lower variance is better
    const mean = counts.reduce((a, b) => a + b, 0) / counts.length
    const variance = counts.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / counts.length
    const score = mean - variance // simple heuristic
    if (score > bestScore) {
      bestScore = score
      best = delim
    }
  }

  return best
}

export function parseCSV(
  text: string,
  opts: { maxRows?: number; delimiter?: CSVDelimiter } = {}
): { rows: string[][]; truncated: boolean } {
  const maxRows = opts.maxRows ?? 201 // 1 header + 200 data rows by default
  const delim = opts.delimiter ?? detectDelimiter(text)
  const input = stripBOM(text)
  const rows: string[][] = []
  let field = ''
  let row: string[] = []
  let inQuotes = false

  const pushField = () => {
    row.push(field)
    field = ''
  }

  const pushRow = () => {
    // Normalize to at least 1 column
    if (row.length === 0) row.push('')
    rows.push(row)
    row = []
  }

  for (let i = 0; i < input.length; i++) {
    const ch = input[i]
    if (inQuotes) {
      if (ch === '"') {
        if (input[i + 1] === '"') {
          field += '"' // escaped quote
          i++
        } else {
          inQuotes = false
        }
      } else {
        field += ch
      }
      continue
    }

    if (ch === '"') {
      inQuotes = true
    } else if (ch === delim) {
      pushField()
    } else if (ch === '\n') {
      pushField()
      pushRow()
      if (rows.length >= maxRows) break
    } else if (ch === '\r') {
      // Handle CRLF: look ahead for \n and skip it
      if (input[i + 1] === '\n') {
        i++
      }
      pushField()
      pushRow()
      if (rows.length >= maxRows) break
    } else {
      field += ch
    }
  }

  // Flush last field/row if input didn't end with newline
  if (field.length > 0 || row.length > 0) {
    pushField()
    pushRow()
  }

  const truncated = rows.length >= maxRows
  return { rows, truncated }
}

