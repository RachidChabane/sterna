import type { Attachment } from '@/components/models/types'

// Return concatenated text from text/code file attachments
export function buildTextFromTextAttachments(attachments: Attachment[]): string {
  const files = attachments.filter(a => a.type === 'file' && (a as any).textContent) as any[]
  if (files.length === 0) return ''
  return files
    .map(f => `\n\n--- Fichier attaché: ${f.file.name} ---\n${f.textContent}\n--- Fin du fichier ---`)
    .join('')
}
