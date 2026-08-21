/**
 * Spark Parser Utility
 *
 * Parses LLM responses to extract Spark components (interactive React components).
 * Supports two formats:
 * 1. New format: Fenced code blocks with `tsx spark:Title` or `html spark:Title`
 * 2. Legacy format: <spark title="...">code</spark> tags
 */

/**
 * Spark definition extracted from LLM response
 */
export interface SparkDefinition {
  id: string
  title: string
  framework: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv' | 'xlsx'
  code: string
  version: number
}

/**
 * Spark update instruction
 */
export interface SparkUpdateInstruction {
  sparkId: string
  instructions: string
}

// Pattern for new fenced code block format: ```tsx spark:Title or ```html spark:Title
// Matches: ```tsx spark:Title Name\ncode\n``` or ```html spark:Title\ncode\n```
const SPARK_FENCED_PATTERN = /```(tsx|jsx|html|svg)\s+spark:([^\n]+)\n([\s\S]*?)```/gi

// Legacy pattern for spark create tags: <spark title="...">code</spark>
const SPARK_CREATE_PATTERN = /<spark\s+title="([^"]+)"(?:\s+framework="([^"]+)")?\s*>\s*([\s\S]*?)\s*<\/spark>/gi

// Pattern for spark update tags: <spark-update id="...">instructions</spark-update>
const SPARK_UPDATE_PATTERN = /<spark-update\s+id="([^"]+)"\s*>\s*([\s\S]*?)\s*<\/spark-update>/gi

/**
 * Generate a unique spark ID
 */
function generateSparkId(): string {
  return `spark_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`
}

/**
 * Map language identifier to framework
 */
function languageToFramework(lang: string): 'react' | 'html' | 'svg' {
  const langLower = lang.toLowerCase()
  if (langLower === 'tsx' || langLower === 'jsx') {
    return 'react'
  }
  if (langLower === 'svg') {
    return 'svg'
  }
  return 'html'
}

/**
 * Detect framework from code content (fallback)
 */
function detectFramework(code: string): 'react' | 'html' | 'svg' {
  const codeLower = code.toLowerCase()

  // SVG detection
  if (codeLower.includes('<svg') || codeLower.includes('xmlns="http://www.w3.org/2000/svg"')) {
    return 'svg'
  }

  // React detection - look for React-specific patterns
  if (
    codeLower.includes('usestate') ||
    codeLower.includes('useeffect') ||
    codeLower.includes('usememo') ||
    codeLower.includes('usecallback') ||
    codeLower.includes('useref') ||
    codeLower.includes('react.') ||
    codeLower.includes('export default function') ||
    codeLower.includes('export function') ||
    codeLower.includes('return (') ||
    codeLower.includes('classname=')
  ) {
    return 'react'
  }

  // Default to HTML
  return 'html'
}

/**
 * Extract sparks from LLM response content
 * Supports both new fenced code block format and legacy <spark> tags
 *
 * @param content - The LLM response content
 * @returns Array of extracted spark definitions
 */
export function extractSparks(content: string): SparkDefinition[] {
  const sparks: SparkDefinition[] = []
  const seenCodes = new Set<string>()

  // First, try new fenced code block format: ```tsx spark:Title
  SPARK_FENCED_PATTERN.lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = SPARK_FENCED_PATTERN.exec(content)) !== null) {
    const language = match[1]
    const title = match[2].trim()
    const code = match[3].trim()

    // Avoid duplicates
    const codeHash = code.substring(0, 100)
    if (seenCodes.has(codeHash)) continue
    seenCodes.add(codeHash)

    const framework = languageToFramework(language)

    sparks.push({
      id: generateSparkId(),
      title,
      framework,
      code,
      version: 1,
    })
  }

  // Then, try legacy format: <spark title="...">code</spark>
  SPARK_CREATE_PATTERN.lastIndex = 0

  while ((match = SPARK_CREATE_PATTERN.exec(content)) !== null) {
    const title = match[1]
    const explicitFramework = match[2] as 'react' | 'html' | 'svg' | undefined
    const code = match[3].trim()

    // Avoid duplicates
    const codeHash = code.substring(0, 100)
    if (seenCodes.has(codeHash)) continue
    seenCodes.add(codeHash)

    // Detect or use explicit framework
    const framework = explicitFramework || detectFramework(code)

    sparks.push({
      id: generateSparkId(),
      title,
      framework,
      code,
      version: 1,
    })
  }

  return sparks
}

/**
 * Extract spark update instructions from LLM response content
 *
 * @param content - The LLM response content
 * @returns Array of update instructions
 */
export function extractSparkUpdates(content: string): SparkUpdateInstruction[] {
  const updates: SparkUpdateInstruction[] = []

  // Reset regex lastIndex to ensure fresh matching
  SPARK_UPDATE_PATTERN.lastIndex = 0

  let match: RegExpExecArray | null
  while ((match = SPARK_UPDATE_PATTERN.exec(content)) !== null) {
    const sparkId = match[1]
    const instructions = match[2].trim()

    updates.push({
      sparkId,
      instructions,
    })
  }

  return updates
}

/**
 * Check if content contains any spark tags or spark code blocks
 *
 * @param content - The content to check
 * @returns True if content contains spark tags or blocks
 */
export function containsSparks(content: string): boolean {
  // Reset lastIndex for accurate testing
  SPARK_FENCED_PATTERN.lastIndex = 0
  SPARK_CREATE_PATTERN.lastIndex = 0
  SPARK_UPDATE_PATTERN.lastIndex = 0

  return (
    SPARK_FENCED_PATTERN.test(content) ||
    SPARK_CREATE_PATTERN.test(content) ||
    SPARK_UPDATE_PATTERN.test(content)
  )
}

/**
 * Strip spark tags and spark code blocks from content for display
 * Note: We DON'T strip fenced spark blocks since the code is copy-pastable.
 * We only strip legacy <spark> tags.
 *
 * @param content - The content to strip
 * @returns Content with legacy spark tags removed (fenced blocks remain)
 */
export function stripSparkTags(content: string): string {
  // Reset regex lastIndex
  SPARK_CREATE_PATTERN.lastIndex = 0
  SPARK_UPDATE_PATTERN.lastIndex = 0

  return content
    .replace(SPARK_CREATE_PATTERN, '')
    .replace(SPARK_UPDATE_PATTERN, '')
    .trim()
}
