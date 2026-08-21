/**
 * FileDialogs - All dialog components for file operations
 */

import { Input } from '@/components/ui/input'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type {
  NewItemDialogState,
  DeleteDialogState,
  RenameDialogState,
  CloseFileDialogState,
} from './types'

interface FileDialogsProps {
  // New item dialog
  newItemDialog: NewItemDialogState | null
  newItemName: string
  onNewItemNameChange: (name: string) => void
  onCreateNewItem: () => void
  onCancelNewItem: () => void

  // Delete dialog
  deleteDialog: DeleteDialogState | null
  onConfirmDelete: () => void
  onCancelDelete: () => void

  // Rename dialog
  renameDialog: RenameDialogState | null
  renameName: string
  onRenameNameChange: (name: string) => void
  onConfirmRename: () => void
  onCancelRename: () => void

  // Close file dialog
  closeFileDialog: CloseFileDialogState | null
  onConfirmCloseFile: () => void
  onCancelCloseFile: () => void
}

export function FileDialogs({
  newItemDialog,
  newItemName,
  onNewItemNameChange,
  onCreateNewItem,
  onCancelNewItem,
  deleteDialog,
  onConfirmDelete,
  onCancelDelete,
  renameDialog,
  renameName,
  onRenameNameChange,
  onConfirmRename,
  onCancelRename,
  closeFileDialog,
  onConfirmCloseFile,
  onCancelCloseFile,
}: FileDialogsProps) {
  return (
    <>
      {/* New File/Folder Dialog */}
      <AlertDialog open={!!newItemDialog} onOpenChange={onCancelNewItem}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Create New {newItemDialog?.type === 'file' ? 'File' : 'Folder'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Enter a name for the new {newItemDialog?.type}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            value={newItemName}
            onChange={(e) => onNewItemNameChange(e.target.value)}
            placeholder={`${newItemDialog?.type === 'file' ? 'filename.py' : 'folder-name'}`}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onCreateNewItem()
            }}
            autoFocus
          />
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => onNewItemNameChange('')}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onCreateNewItem} disabled={!newItemName.trim()}>
              Create
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteDialog} onOpenChange={onCancelDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Item</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{deleteDialog?.path}"? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirmDelete} className="bg-destructive">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Rename Dialog */}
      <AlertDialog open={!!renameDialog} onOpenChange={onCancelRename}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rename</AlertDialogTitle>
            <AlertDialogDescription>
              Enter a new name for "{renameDialog?.oldName}"
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Input
            value={renameName}
            onChange={(e) => onRenameNameChange(e.target.value)}
            placeholder="New name"
            onKeyDown={(e) => {
              if (e.key === 'Enter') onConfirmRename()
            }}
            autoFocus
          />
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => onRenameNameChange('')}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirmRename} disabled={!renameName.trim()}>
              Rename
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Close File Confirmation Dialog */}
      <AlertDialog open={!!closeFileDialog} onOpenChange={onCancelCloseFile}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unsaved Changes</AlertDialogTitle>
            <AlertDialogDescription>
              "{closeFileDialog?.name}" has unsaved changes. Do you want to close it anyway?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirmCloseFile} className="bg-destructive hover:bg-destructive/90">
              Close Anyway
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
