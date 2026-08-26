import type { Attachment, FileAttachment } from '@/components/models/types'

const isFileAttachment = (a: Attachment): a is FileAttachment => a.type === 'file'

// Return concatenated text from text/code file attachments
export function buildTextFromTextAttachments(attachments: Attachment[]): string {
  const files = attachments.filter(isFileAttachment).filter((f) => f.textContent)
  if (files.length === 0) return ''
  return files
    .map(f => `\n\n--- Fichier attaché: ${f.file.name} ---\n${f.textContent}\n--- Fin du fichier ---`)
    .join('')
}
