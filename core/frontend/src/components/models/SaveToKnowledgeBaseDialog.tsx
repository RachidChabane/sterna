import { Loader2, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface SaveToKnowledgeBaseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  isSaving: boolean
  onConfirm: () => void
}

export function SaveToKnowledgeBaseDialog({ open, onOpenChange, isSaving, onConfirm }: SaveToKnowledgeBaseDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Save to Knowledge Base</DialogTitle>
          <DialogDescription>
            Save this conversation to your knowledge base? This will make the conversation content searchable by AI.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={isSaving}>
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <BookOpen className="h-4 w-4 mr-2" />
                Save
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
