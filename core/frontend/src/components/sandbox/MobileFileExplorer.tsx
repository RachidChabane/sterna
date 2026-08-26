/**
 * Mobile file explorer: the file tree rendered inside a slide-in Sheet,
 * used instead of the desktop sidebar below the mobile breakpoint.
 * File-tree actions that navigate away (open, new file/folder) also
 * close the sheet.
 */

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { FileTreePanel } from './FileTreePanel'
import type { DeleteDialogState, FileNode, NewItemDialogState, RenameDialogState } from './types'

// Narrow slice of useFileTree — only what the mobile explorer sheet needs.
interface FileTreeOps {
  fileTree: FileNode[]
  isLoadingTree: boolean
  selectedPath: string | null
  showHiddenFiles: boolean
  setSelectedPath: (path: string | null) => void
  toggleDirectory: (path: string) => void
  setShowHiddenFiles: (show: boolean) => void
  loadFileTree: (preserveOpenState?: boolean, additionalOpenPaths?: string[]) => Promise<void>
  getParentPathForNewItem: () => string
}

interface MobileFileExplorerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileTreeHook: FileTreeOps
  gitModifiedFiles?: string[]
  openFile: (path: string, name: string) => void
  setNewItemDialog: (dialog: NewItemDialogState | null) => void
  setRenameDialog: (dialog: RenameDialogState | null) => void
  setRenameName: (name: string) => void
  setDeleteDialog: (dialog: DeleteDialogState | null) => void
  showFileDetails: (path: string, name: string) => void
  downloadFile: (path: string, name: string) => void
  downloadWorkspace: () => void
  handleImportClick: () => void
  moveItem: (draggedNode: FileNode, targetNode: FileNode) => void
}

export function MobileFileExplorer({
  open,
  onOpenChange,
  fileTreeHook,
  gitModifiedFiles,
  openFile,
  setNewItemDialog,
  setRenameDialog,
  setRenameName,
  setDeleteDialog,
  showFileDetails,
  downloadFile,
  downloadWorkspace,
  handleImportClick,
  moveItem,
}: MobileFileExplorerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-[85vw] max-w-[320px] p-0">
        <SheetHeader className="px-4 py-3 border-b">
          <SheetTitle className="text-sm font-medium">Explorer</SheetTitle>
        </SheetHeader>
        <div className="h-[calc(100vh-60px)]">
          <FileTreePanel
            fileTree={fileTreeHook.fileTree}
            isLoadingTree={fileTreeHook.isLoadingTree}
            selectedPath={fileTreeHook.selectedPath}
            isSidebarCollapsed={false}
            sidebarWidth={320}
            isResizing={false}
            showHiddenFiles={fileTreeHook.showHiddenFiles}
            isMobileSheet={true}
            modifiedFilePaths={gitModifiedFiles}
            onSelectPath={fileTreeHook.setSelectedPath}
            onToggleDirectory={fileTreeHook.toggleDirectory}
            onOpenFile={(path, name) => {
              openFile(path, name)
              onOpenChange(false)
            }}
            onNewFile={(parentPath) => {
              setNewItemDialog({ open: true, type: 'file', parentPath })
              onOpenChange(false)
            }}
            onNewFolder={(parentPath) => {
              setNewItemDialog({ open: true, type: 'folder', parentPath })
              onOpenChange(false)
            }}
            onRename={(path, oldName) => {
              setRenameDialog({ open: true, path, oldName })
              setRenameName(oldName)
            }}
            onDelete={(path) => setDeleteDialog({ open: true, path })}
            onShowDetails={showFileDetails}
            onDownload={downloadFile}
            onDownloadWorkspace={downloadWorkspace}
            onImport={handleImportClick}
            onMove={moveItem}
            onToggleSidebar={() => {}}
            onToggleShowHiddenFiles={() => {
              fileTreeHook.setShowHiddenFiles(!fileTreeHook.showHiddenFiles)
              setTimeout(() => fileTreeHook.loadFileTree(), 0)
            }}
            onStartResize={() => {}}
            getParentPathForNewItem={fileTreeHook.getParentPathForNewItem}
          />
        </div>
      </SheetContent>
    </Sheet>
  )
}
