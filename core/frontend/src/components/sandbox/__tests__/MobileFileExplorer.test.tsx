import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { MobileFileExplorer } from '../MobileFileExplorer'
import type { FileNode } from '../types'

function makeFileTreeHook() {
  const fileTree: FileNode[] = [{ name: 'app.py', path: '/workspace/app.py', type: 'file' }]
  return {
    fileTree,
    isLoadingTree: false,
    selectedPath: null,
    showHiddenFiles: false,
    setSelectedPath: vi.fn(),
    toggleDirectory: vi.fn(),
    setShowHiddenFiles: vi.fn(),
    loadFileTree: vi.fn().mockResolvedValue(undefined),
    getParentPathForNewItem: vi.fn().mockReturnValue('/workspace'),
  }
}

describe('MobileFileExplorer', () => {
  it('renders the Explorer sheet with the file tree when open', () => {
    render(
      <MobileFileExplorer
        open={true}
        onOpenChange={vi.fn()}
        fileTreeHook={makeFileTreeHook()}
        openFile={vi.fn()}
        setNewItemDialog={vi.fn()}
        setRenameDialog={vi.fn()}
        setRenameName={vi.fn()}
        setDeleteDialog={vi.fn()}
        showFileDetails={vi.fn()}
        downloadFile={vi.fn()}
        downloadWorkspace={vi.fn()}
        handleImportClick={vi.fn()}
        moveItem={vi.fn()}
      />
    )

    expect(screen.getByText('Explorer')).toBeInTheDocument()
    expect(screen.getByText('app.py')).toBeInTheDocument()
  })

  it('renders nothing when closed', () => {
    render(
      <MobileFileExplorer
        open={false}
        onOpenChange={vi.fn()}
        fileTreeHook={makeFileTreeHook()}
        openFile={vi.fn()}
        setNewItemDialog={vi.fn()}
        setRenameDialog={vi.fn()}
        setRenameName={vi.fn()}
        setDeleteDialog={vi.fn()}
        showFileDetails={vi.fn()}
        downloadFile={vi.fn()}
        downloadWorkspace={vi.fn()}
        handleImportClick={vi.fn()}
        moveItem={vi.fn()}
      />
    )

    expect(screen.queryByText('Explorer')).not.toBeInTheDocument()
  })

  it('opening a file also closes the sheet', () => {
    const openFile = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <MobileFileExplorer
        open={true}
        onOpenChange={onOpenChange}
        fileTreeHook={makeFileTreeHook()}
        openFile={openFile}
        setNewItemDialog={vi.fn()}
        setRenameDialog={vi.fn()}
        setRenameName={vi.fn()}
        setDeleteDialog={vi.fn()}
        showFileDetails={vi.fn()}
        downloadFile={vi.fn()}
        downloadWorkspace={vi.fn()}
        handleImportClick={vi.fn()}
        moveItem={vi.fn()}
      />
    )

    fireEvent.click(screen.getByText('app.py'))

    expect(openFile).toHaveBeenCalledWith('/workspace/app.py', 'app.py')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
