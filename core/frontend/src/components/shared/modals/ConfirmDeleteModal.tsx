import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

interface ConfirmDeleteModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: (deleteWorkspace?: boolean) => void
  title?: string
  description?: string
  itemName?: string
  showWorkspaceCheckbox?: boolean
  workspaceCheckboxLabel?: string
}

export function ConfirmDeleteModal({
  isOpen,
  onClose,
  onConfirm,
  title = 'Delete',
  description = 'Are you sure you want to delete this? This action cannot be undone.',
  itemName,
  showWorkspaceCheckbox = false,
  workspaceCheckboxLabel = 'Delete workspace files'
}: ConfirmDeleteModalProps) {
  const [deleteWorkspace, setDeleteWorkspace] = useState(true)

  const handleConfirm = () => {
    onConfirm(showWorkspaceCheckbox ? deleteWorkspace : undefined)
    onClose()
    // Reset checkbox state after closing
    setDeleteWorkspace(true)
  }

  const handleClose = () => {
    onClose()
    // Reset checkbox state when canceling
    setDeleteWorkspace(true)
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {itemName ? (
              <>
                Are you sure you want to delete <strong>{itemName}</strong>? This action cannot be undone.
              </>
            ) : (
              description
            )}
          </DialogDescription>
        </DialogHeader>

        {showWorkspaceCheckbox && (
          <div className="flex items-center space-x-2 py-3">
            <Checkbox
              id="delete-workspace"
              checked={deleteWorkspace}
              onCheckedChange={(checked) => setDeleteWorkspace(checked as boolean)}
            />
            <Label
              htmlFor="delete-workspace"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
            >
              {workspaceCheckboxLabel}
            </Label>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            variant="destructive"
            className="bg-destructive hover:bg-destructive/90"
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
