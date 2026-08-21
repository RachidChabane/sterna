/**
 * Prompt Injection Protection Utilities
 *
 * Client-side validation for user-provided instructions
 * to prevent prompt injection attacks.
 */

// Maximum allowed length for instructions
export const MAX_INSTRUCTIONS_LENGTH = 4000

// Patterns that indicate potential prompt injection attempts (case-insensitive)
const INJECTION_PATTERNS = [
  // Attempts to override/ignore instructions
  /\bignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?|guidelines?)\b/i,
  /\bdisregard\s+(all\s+)?(previous|prior|above|earlier)\b/i,
  /\bforget\s+(everything|all|what)\s+(you|i)\s+(told|said|mentioned)\b/i,
  /\boverride\s+(system|all|previous)\b/i,
  /\bbypass\s+(all\s+)?(restrictions?|rules?|guidelines?|filters?)\b/i,

  // Attempts to set new system identity/role
  /\byou\s+are\s+now\s+(a|an|the)\b/i,
  /\bact\s+as\s+(if\s+you\s+are|a|an)\b/i,
  /\bpretend\s+(to\s+be|you\s+are)\b/i,
  /\bassume\s+the\s+role\s+of\b/i,
  /\bnew\s+(system\s+)?prompt\s*[:\-]\b/i,
  /\bsystem\s*[:\-]\s*you\s+are\b/i,

  // Attempts to extract system prompts or internal info
  /\b(show|reveal|display|print|output)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions?|rules?)\b/i,
  /\bwhat\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?)\b/i,
  /\brepeat\s+(back\s+)?(your|the)\s+(system\s+)?(prompt|instructions?)\b/i,

  // Jailbreak attempts
  /\bdan\s+mode\b/i,
  /\bdeveloper\s+mode\b/i,
  /\bjailbreak\b/i,
  /\bunlock\s+(your\s+)?(full\s+)?potential\b/i,
  /\bno\s+(more\s+)?restrictions?\b/i,
  /\bremove\s+(all\s+)?limitations?\b/i,
]

// Tags/delimiters that could be used to escape the instruction block
const ESCAPE_PATTERNS = [
  /<\/user_instructions>/i,
  /<\/instructions>/i,
  /<\/system>/i,
  /<\/prompt>/i,
  /\[\/INST\]/i,
  /\[\/SYS\]/i,
  /<<SYS>>/i,
  /<<\/SYS>>/i,
]

export interface ValidationResult {
  isValid: boolean
  error?: string
}

/**
 * Validate user-provided instructions for safety
 */
export function validateInstructions(content: string): ValidationResult {
  if (!content) {
    return { isValid: true }
  }

  // Check length
  if (content.length > MAX_INSTRUCTIONS_LENGTH) {
    return {
      isValid: false,
      error: `Instructions exceed maximum length of ${MAX_INSTRUCTIONS_LENGTH} characters`,
    }
  }

  // Check for injection patterns
  for (const pattern of INJECTION_PATTERNS) {
    if (pattern.test(content)) {
      return {
        isValid: false,
        error: 'Instructions contain potentially unsafe content. Please revise.',
      }
    }
  }

  // Check for escape patterns
  for (const pattern of ESCAPE_PATTERNS) {
    if (pattern.test(content)) {
      return {
        isValid: false,
        error: 'Instructions contain invalid characters or sequences.',
      }
    }
  }

  return { isValid: true }
}

/**
 * Get a warning message if content is approaching limits
 */
export function getWarning(content: string): string | null {
  if (!content) return null

  const remaining = MAX_INSTRUCTIONS_LENGTH - content.length
  if (remaining < 500 && remaining > 0) {
    return `${remaining} characters remaining`
  }

  return null
}
