/**
 * File utility functions for handling file attachments
 */

const MAX_FILE_SIZE_MB = 10
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

// PDF files - sent as binary with file-parser plugin
const PDF_FORMATS = [
  'application/pdf'
]

// Text files - content is read and inserted into message
const TEXT_FORMATS = [
  'text/plain',
  'text/csv',
  'application/json',
  'text/markdown',
  'text/html',
  'application/xml',
  'text/xml',
  'application/rtf' // RTF is technically binary but often readable
]

// Microsoft Office formats - sent as binary documents
const OFFICE_FORMATS = [
  // Modern Office (Open XML)
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/vnd.openxmlformats-officedocument.wordprocessingml.template', // .dotx
  'application/vnd.ms-word.document.macroEnabled.12', // .docm
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
  'application/vnd.openxmlformats-officedocument.spreadsheetml.template', // .xltx
  'application/vnd.ms-excel.sheet.macroEnabled.12', // .xlsm
  'application/vnd.ms-excel.sheet.binary.macroEnabled.12', // .xlsb
  'application/vnd.openxmlformats-officedocument.presentationml.presentation', // .pptx
  'application/vnd.openxmlformats-officedocument.presentationml.template', // .potx
  'application/vnd.ms-powerpoint.presentation.macroEnabled.12', // .pptm

  // Old Office (Binary)
  'application/msword', // .doc
  'application/vnd.ms-excel', // .xls
  'application/vnd.ms-powerpoint', // .ppt

  // LibreOffice/OpenOffice
  'application/vnd.oasis.opendocument.text', // .odt
  'application/vnd.oasis.opendocument.spreadsheet', // .ods
  'application/vnd.oasis.opendocument.presentation', // .odp
  'application/vnd.oasis.opendocument.graphics', // .odg
]

// Office file extensions (for detection when MIME type is generic)
const OFFICE_EXTENSIONS = [
  '.docx', '.doc', '.docm', '.dotx',
  '.xlsx', '.xls', '.xlsm', '.xlsb', '.xltx',
  '.pptx', '.ppt', '.pptm', '.potx',
  '.odt', '.ods', '.odp', '.odg'
]

// Code file extensions - all treated as text files
const CODE_FILE_EXTENSIONS = [
  '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',  // JavaScript/TypeScript
  '.py', '.pyw', '.pyi',                         // Python
  '.java',                                        // Java
  '.c', '.cpp', '.cc', '.cxx', '.h', '.hpp',     // C/C++
  '.cs',                                          // C#
  '.php',                                         // PHP
  '.rb', '.rake',                                 // Ruby
  '.go',                                          // Go
  '.rs',                                          // Rust
  '.swift',                                       // Swift
  '.kt', '.kts',                                  // Kotlin
  '.scala',                                       // Scala
  '.sql',                                         // SQL
  '.sh', '.bash', '.zsh', '.fish',               // Shell
  '.yaml', '.yml', '.toml', '.ini', '.env', '.cfg', '.conf', // Config
  '.gitignore', '.gitattributes', '.dockerignore', '.editorconfig', // Git/Editor config
  '.dockerfile',                                  // Docker
  '.css', '.scss', '.sass', '.less',             // Stylesheets
  '.md', '.markdown', '.mdx',                    // Markdown
  '.txt', '.csv', '.json', '.html', '.htm', '.xml', // Data/Markup
  '.vue', '.svelte', '.astro',                   // Frontend frameworks
  '.r', '.dart', '.lua', '.pl', '.vim',          // Other languages
  '.log'                                          // Log files
]

const SUPPORTED_FORMATS = [...PDF_FORMATS, ...TEXT_FORMATS, ...OFFICE_FORMATS]

export interface FileValidationResult {
  valid: boolean
  error?: string
}

/**
 * Validate a file
 */
export function validateFile(file: File): FileValidationResult {
  // Check file size
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return {
      valid: false,
      error: `File size must be less than ${MAX_FILE_SIZE_MB}MB`
    }
  }

  // Check if format is supported (MIME type or file extension)
  const hasCodeExtension = CODE_FILE_EXTENSIONS.some(ext =>
    file.name.toLowerCase().endsWith(ext)
  )

  const hasOfficeExtension = OFFICE_EXTENSIONS.some(ext =>
    file.name.toLowerCase().endsWith(ext)
  )

  if (!SUPPORTED_FORMATS.includes(file.type) && !hasCodeExtension && !hasOfficeExtension) {
    return {
      valid: false,
      error: `Unsupported file format. Supported: Images, PDFs, Office docs, text/code files`
    }
  }

  return { valid: true }
}

/**
 * Convert a file to base64 data URL
 */
export function convertFileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = () => {
      const result = reader.result as string
      resolve(result)
    }

    reader.onerror = () => {
      reject(new Error('Failed to read file'))
    }

    reader.readAsDataURL(file)
  })
}

/**
 * Get a human-readable file size string
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Get file extension from filename
 */
export function getFileExtension(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toUpperCase() : 'FILE'
}

/**
 * Check if a file is a PDF (sent as binary with file-parser plugin)
 */
export function isPDFFile(file: File): boolean {
  return PDF_FORMATS.includes(file.type) || file.name.toLowerCase().endsWith('.pdf')
}

/**
 * Check if a file is an Office document (Word, Excel, PowerPoint, LibreOffice)
 */
export function isOfficeFile(file: File): boolean {
  return OFFICE_FORMATS.includes(file.type) ||
         OFFICE_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext))
}

/**
 * Check if a file is a text file (content read and inserted into message)
 */
export function isTextFile(file: File): boolean {
  return TEXT_FORMATS.includes(file.type) ||
         CODE_FILE_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext))
}

/**
 * Read a file as text
 */
export function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = () => {
      const result = reader.result as string
      resolve(result)
    }

    reader.onerror = () => {
      reject(new Error('Failed to read file as text'))
    }

    reader.readAsText(file)
  })
}

/**
 * Get a preview of file content (first N lines)
 */
export function getFilePreview(content: string, maxLines: number = 10): { preview: string; isTruncated: boolean; additionalLines: number } {
  const lines = content.split('\n')

  if (lines.length <= maxLines) {
    return {
      preview: content,
      isTruncated: false,
      additionalLines: 0
    }
  }

  const preview = lines.slice(0, maxLines).join('\n')
  return {
    preview,
    isTruncated: true,
    additionalLines: lines.length - maxLines
  }
}

/**
 * Detect programming language from filename for syntax highlighting
 */
export function getLanguageFromFilename(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()

  const languageMap: Record<string, string> = {
    // JavaScript/TypeScript
    'js': 'javascript',
    'jsx': 'jsx',
    'ts': 'typescript',
    'tsx': 'tsx',
    'mjs': 'javascript',
    'cjs': 'javascript',

    // Web
    'html': 'html',
    'htm': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'less': 'less',

    // Data formats
    'json': 'json',
    'xml': 'xml',
    'yaml': 'yaml',
    'yml': 'yaml',
    'csv': 'csv',

    // Markup
    'md': 'markdown',
    'markdown': 'markdown',

    // Python
    'py': 'python',
    'pyw': 'python',

    // Other languages
    'java': 'java',
    'c': 'c',
    'cpp': 'cpp',
    'cs': 'csharp',
    'php': 'php',
    'rb': 'ruby',
    'go': 'go',
    'rs': 'rust',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',
    'sql': 'sql',
    'sh': 'bash',
    'bash': 'bash',
    'zsh': 'bash',

    // Config files
    'dockerfile': 'dockerfile',
    'gitignore': 'gitignore',
    'env': 'bash',

    // Plain text
    'txt': 'text'
  }

  return ext ? languageMap[ext] || 'text' : 'text'
}

