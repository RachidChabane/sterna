import { useState } from 'react'
import { Upload } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { subAgentApi } from '@/api/subAgents'
import { useSubAgentStore } from '@/store/subAgentStore'
import { toast } from 'sonner'

interface ImportAgentDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function ImportAgentDialog({ open, onOpenChange }: ImportAgentDialogProps) {
  const [content, setContent] = useState('')
  const [importing, setImporting] = useState(false)
  const { fetchAgents } = useSubAgentStore()

  const handleImport = async () => {
    if (!content.trim()) {
      toast.error('Paste markdown content to import')
      return
    }

    setImporting(true)
    try {
      await subAgentApi.importMd(content)
      toast.success('Agent imported successfully')
      await fetchAgents(true)
      setContent('')
      onOpenChange(false)
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Import failed'
      toast.error(msg)
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-4 w-4" />
            Import Agent from Markdown
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            Paste a Claude Code agent markdown file with YAML frontmatter.
          </p>
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={`---\nname: my-agent\ndescription: A helpful agent\nmodel: sonnet\ntools:\n  - Read\n  - Grep\n---\n\nYour system prompt here...`}
            className="min-h-[300px] font-mono text-xs"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={importing || !content.trim()}>
            {importing ? 'Importing...' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
