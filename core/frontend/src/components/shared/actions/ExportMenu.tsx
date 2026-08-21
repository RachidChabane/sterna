import { DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { Copy, Download } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'

export type ExportFormat = 'json' | 'txt' | 'csv'

interface ExportMenuProps {
  data: unknown
  filename: string
  formats?: ExportFormat[]
  copyOptions?: {
    text?: boolean
    metadata?: boolean
  }
  onCopy?: (type: 'text' | 'metadata') => string
  onExport?: (type: 'text' | 'metadata') => string
}

export function ExportMenu({
  data,
  filename,
  formats = ['json', 'txt'],
  copyOptions,
  onCopy,
  onExport,
}: ExportMenuProps) {
  const { toast } = useToast()

  const handleCopy = (type: 'text' | 'metadata') => {
    const content = onCopy?.(type) ?? (type === 'metadata' ? JSON.stringify(data, null, 2) : String(data))
    navigator.clipboard.writeText(content)
    toast({
      title: 'Copied to clipboard',
      description: `${type === 'metadata' ? 'Metadata' : 'Text'} copied successfully`,
    })
  }

  const handleExport = (format: ExportFormat, type: 'text' | 'metadata') => {
    const content = onExport?.(type) ?? (type === 'metadata' ? JSON.stringify(data, null, 2) : String(data))
    const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.${format}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <>
      {/* Copy options */}
      {copyOptions?.text && (
        <DropdownMenuItem onClick={() => handleCopy('text')}>
          <Copy className="h-4 w-4 mr-2" /> Copy responses
        </DropdownMenuItem>
      )}
      {copyOptions?.metadata && (
        <DropdownMenuItem onClick={() => handleCopy('metadata')}>
          <Copy className="h-4 w-4 mr-2" /> Copy metadata (JSON)
        </DropdownMenuItem>
      )}

      {/* Export options */}
      {formats.includes('txt') && (
        <DropdownMenuItem onClick={() => handleExport('txt', 'text')}>
          <Download className="h-4 w-4 mr-2" /> Export responses (.txt)
        </DropdownMenuItem>
      )}
      {formats.includes('json') && (
        <DropdownMenuItem onClick={() => handleExport('json', 'metadata')}>
          <Download className="h-4 w-4 mr-2" /> Export metadata (.json)
        </DropdownMenuItem>
      )}
      {formats.includes('csv') && (
        <DropdownMenuItem onClick={() => handleExport('csv', 'metadata')}>
          <Download className="h-4 w-4 mr-2" /> Export data (.csv)
        </DropdownMenuItem>
      )}
    </>
  )
}
