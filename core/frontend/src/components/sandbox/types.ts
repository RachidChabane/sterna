/**
 * Shared types for FullIDE components
 */

// Git status for file coloring in the file tree
type FileGitStatus = 'new' | 'modified' | 'staged' | 'untracked' | undefined

export interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileNode[]
  isOpen?: boolean
  gitStatus?: FileGitStatus
}

export interface OpenFile {
  path: string
  name: string
  content: string
  language: string
  isDirty: boolean
}

export interface ExecutionResult {
  output: string
  error?: string
  exit_code: number
  execution_time: number
}

export interface NewItemDialogState {
  open: boolean
  type: 'file' | 'folder'
  parentPath: string
}

export interface DeleteDialogState {
  open: boolean
  path: string
}

export interface RenameDialogState {
  open: boolean
  path: string
  oldName: string
}

export interface CloseFileDialogState {
  open: boolean
  path: string
  name: string
}

const LANGUAGE_MAP: Record<string, string> = {
  'py': 'python',
  'js': 'javascript',
  'ts': 'typescript',
  'jsx': 'javascript',
  'tsx': 'typescript',
  'json': 'json',
  'md': 'markdown',
  'html': 'html',
  'css': 'css',
  'sh': 'shell',
  'bash': 'shell',
}

export const getLanguageFromPath = (path: string): string => {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  return LANGUAGE_MAP[ext] || 'plaintext'
}

export const getExecutableLanguage = (path: string): string | null => {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (ext === 'py') return 'python'
  if (ext === 'js') return 'javascript'
  if (ext === 'sh' || ext === 'bash') return 'bash'
  return null
}

// File extensions that support preview mode (split/preview views)
const PREVIEWABLE_EXTENSIONS = new Set([
  'html', 'htm', 'md', 'markdown',
  'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico',
  'pdf', 'csv', 'xlsx', 'xls', 'xlsm'
])

// Binary files that should auto-open in preview mode (no code view available)
const BINARY_PREVIEWABLE_EXTENSIONS = new Set([
  'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico',
  'pdf', 'xlsx', 'xls', 'xlsm'
])

/**
 * Check if a file type supports preview mode (split/preview views)
 */
export const supportsPreview = (fileName: string): boolean => {
  const ext = fileName.toLowerCase().split('.').pop() || ''
  return PREVIEWABLE_EXTENSIONS.has(ext)
}

/**
 * Check if a file is binary and should auto-open in preview mode
 * These files don't have a code view - only preview is available
 */
export const isBinaryPreviewable = (fileName: string): boolean => {
  const ext = fileName.toLowerCase().split('.').pop() || ''
  return BINARY_PREVIEWABLE_EXTENSIONS.has(ext)
}
