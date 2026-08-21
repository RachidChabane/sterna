import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface RenameModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: (newName: string) => void
  currentName: string
  title?: string
  description?: string
  inputPlaceholder?: string
}

export function RenameModal({
  isOpen,
  onClose,
  onConfirm,
  currentName,
  title = 'Rename',
  description = 'Enter a new name',
  inputPlaceholder = 'Name'
}: RenameModalProps) {
  const [value, setValue] = useState(currentName)

  // Update value when currentName changes
  useEffect(() => {
    setValue(currentName)
  }, [currentName])

  const handleSubmit = () => {
    if (value.trim()) {
      onConfirm(value.trim())
      onClose()
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSubmit()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={inputPlaceholder}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            className="bg-accent-brand hover:shadow-glow-brand text-white"
            disabled={!value.trim()}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
