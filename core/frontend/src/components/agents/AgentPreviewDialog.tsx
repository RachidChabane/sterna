import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface AgentPreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  markdown: string
  filename: string
}

export default function AgentPreviewDialog({
  open,
  onOpenChange,
  markdown,
  filename,
}: AgentPreviewDialogProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(markdown)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {filename}
            <Button variant="ghost" size="sm" className="h-7 px-2" onClick={handleCopy}>
              {copied ? (
                <Check className="h-3.5 w-3.5 text-green-500" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </Button>
          </DialogTitle>
        </DialogHeader>
        <pre className="overflow-auto rounded-lg bg-muted/50 p-4 text-xs font-mono leading-relaxed max-h-[60vh]">
          {markdown}
        </pre>
      </DialogContent>
    </Dialog>
  )
}
