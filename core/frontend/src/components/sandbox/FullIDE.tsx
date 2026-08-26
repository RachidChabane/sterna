/**
 * FullIDE Component
 *
 * Complete IDE with file tree, multi-tab editor, and code execution.
 * Isolated per user × chat with persistent file system in sandbox container.
 *
 * This component composes feature hooks (file operations, upload,
 * execution, editor lifecycle, workspace persistence, preview panel,
 * keyboard shortcuts, sidebar resize) and stays focused on layout and
 * wiring — the behavior itself lives in ./hooks and the small feature
 * components it renders.
 */

import { useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { FileCode, Play, StopCircle, X, FolderOpen, Search, Terminal, Globe, Loader2 } from 'lucide-react'
import { StatusBar } from './StatusBar'
import { Breadcrumbs } from './Breadcrumbs'
import { QuickFileSearch } from './QuickFileSearch'
import { GlobalSearch } from './GlobalSearch'
import { KeyboardShortcuts, getPlatformShortcuts } from './KeyboardShortcuts'
import { BottomPanel } from './BottomPanel'
import { cn } from '@/lib/utils'
import { useToast } from '@/hooks/use-toast'
import { getPreviewUrl } from '@/api/sandbox'
import { Button } from '@/components/ui/button'
import { useSettingsStore } from '@/store/settingsStore'

// Import types and utilities
import { getExecutableLanguage, supportsPreview, isBinaryPreviewable } from './types'

// Import custom hooks
import {
  useFileTree,
  useMonacoEditor,
  useIDEState,
  useFileUpload,
  useFileOperations,
  useCodeExecution,
  useEditorMount,
  useWorkspaceRestore,
  usePreviewPanel,
  useIDEKeyboardShortcuts,
  useSidebarResize,
} from './hooks'

// Import components
import { EditorTabs } from './EditorTabs'
import { FileTreePanel } from './FileTreePanel'
import { FileDialogs } from './FileDialogs'
import { FileDetailsModal } from './FileDetailsModal'
import { MessageViewModal } from './MessageViewModal'
import { SplitView, type ViewMode } from './SplitView'
import { FilePreview } from './FilePreview'
import { ResourceBars } from './ResourceBars'
import { IDEUploadOverlays } from './IDEUploadOverlays'
import { MobileFileExplorer } from './MobileFileExplorer'
import type { Message } from '@/components/models/types'

export interface FullIDEProps {
  userId?: string
  chatId?: string
  conversationId?: string
  sessionId?: string  // Code session ID for code sessions mode
  className?: string
  messages?: Message[]  // Optional: messages from the chat to enable message navigation
  mode?: 'chat' | 'code'  // Operation mode: 'chat' for sandbox, 'code' for code sessions
  readOnly?: boolean  // For viewing diffs without editing
  workspacePath?: string  // Override workspace path (e.g., for code sessions)
  onFileChange?: (path: string, content: string) => void  // Callback when file changes
  // Git integration props (for code sessions)
  gitBranches?: Array<{ name: string; protected?: boolean }>
  gitCurrentBranch?: string
  gitIsLoadingBranches?: boolean
  gitModifiedFiles?: string[]
  onGitBranchSelect?: (branch: string) => void
  onGitCreateBranch?: (branchName: string, fromBranch: string) => Promise<void>
}

export function FullIDE({
  userId,
  chatId,
  conversationId,
  sessionId,
  className,
  messages = [],
  mode = 'chat',
  readOnly = false,
  workspacePath,
  onFileChange,
  // Git props
  gitBranches,
  gitCurrentBranch,
  gitIsLoadingBranches,
  gitModifiedFiles,
  onGitBranchSelect,
  onGitCreateBranch,
}: FullIDEProps) {
  const { toast } = useToast()
  // For code sessions, use sessionId as projectId; for chats, use chatId or conversationId
  const projectId = mode === 'code' && sessionId ? sessionId : (chatId || conversationId || 'default')
  // Workspace path - the orchestrator adds the chat workspace prefix automatically
  const effectiveWorkspacePath = workspacePath || '/workspace'

  // Custom hooks
  const fileTreeHook = useFileTree({
    userId,
    conversationId,
    chatId,
    sessionId,
    mode,
    workspacePath: effectiveWorkspacePath,
  })
  const editorHook = useMonacoEditor()

  const fileOps = useFileOperations({ userId, projectId, toast, fileTreeHook, editorHook })

  // IDE state persistence
  const ideState = useIDEState({
    projectId,
    openFiles: fileOps.openFiles,
    activeFilePath: fileOps.activeFilePath,
    selectedPath: fileTreeHook.selectedPath,
    fileTree: fileTreeHook.fileTree,
  })

  useWorkspaceRestore({
    userId,
    projectId,
    fileTreeHook,
    ideState,
    setOpenFiles: fileOps.setOpenFiles,
    setActiveFilePath: fileOps.setActiveFilePath,
  })

  const upload = useFileUpload({ userId, projectId, toast, loadFileTree: fileTreeHook.loadFileTree })

  const rootRef = useRef<HTMLDivElement | null>(null)
  const sidebar = useSidebarResize({ rootRef })

  // UI state
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('code')
  const [isMobile, setIsMobile] = useState(false)
  const [mobileExplorerOpen, setMobileExplorerOpen] = useState(false)
  const [quickSearchOpen, setQuickSearchOpen] = useState(false)
  const [globalSearchOpen, setGlobalSearchOpen] = useState(false)
  const [bottomPanelOpen, setBottomPanelOpen] = useState(false)
  const [bottomPanelHeight, setBottomPanelHeight] = useState(250)
  const [bottomPanelTab, setBottomPanelTab] = useState<'output' | 'terminal' | 'commits' | 'changes' | 'ports'>('output')
  const [containerHeight, setContainerHeight] = useState(0)
  const codeThemeId = useSettingsStore((s) => s.codeTheme)

  const preview = usePreviewPanel({ userId })

  const openOutputPanel = () => {
    setBottomPanelOpen(true)
    setBottomPanelTab('output')
  }

  const exec = useCodeExecution({
    activeFile: fileOps.activeFile,
    userId,
    projectId,
    toast,
    saveFile: fileOps.saveFile,
    onBeforeRun: openOutputPanel,
  })

  const editorMount = useEditorMount({
    editorHook,
    codeThemeId,
    toast,
    userId,
    projectId,
    activeFilePath: fileOps.activeFilePath,
    activeFile: fileOps.activeFile,
    openFilesRef: fileOps.openFilesRef,
    setOpenFiles: fileOps.setOpenFiles,
  })

  // Detect mobile via media query
  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)')
    setIsMobile(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  // Track container height for bottom panel max height
  useEffect(() => {
    if (!rootRef.current) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height)
      }
    })

    observer.observe(rootRef.current)
    // Set initial height
    setContainerHeight(rootRef.current.clientHeight)

    return () => observer.disconnect()
  }, [])

  // Platform detection for shortcuts
  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform)
  const platformShortcuts = getPlatformShortcuts(isMac)

  const activeFile = fileOps.activeFile

  // Auto-switch view mode based on file type
  useEffect(() => {
    if (!activeFile) return

    // Binary files (images, PDFs) should auto-open in preview mode
    if (isBinaryPreviewable(activeFile.name)) {
      if (viewMode === 'code') {
        setViewMode('preview')
      }
    }
    // Files that don't support preview should stay in code mode
    else if (!supportsPreview(activeFile.name) && viewMode !== 'code') {
      setViewMode('code')
    }
    // SVG and other text-based files that support preview: allow split view, default to code
  }, [activeFile?.name])

  // Force Monaco layout recalculation when view mode changes
  useEffect(() => {
    // Small delay to ensure the transition animation completes
    const timer = setTimeout(() => {
      editorHook.forceLayout()
    }, 250)

    return () => clearTimeout(timer)
  }, [viewMode, editorHook.forceLayout])

  // Handle message navigation - find message by ID and show in modal
  const [messageViewModal, setMessageViewModal] = useState<{ open: boolean; messageId: string } | null>(null)

  const handleNavigateToMessage = (messageId: string) => {
    const message = messages.find(m => m.message_id === messageId)

    if (message) {
      setMessageViewModal({ open: true, messageId })
    } else {
      toast({
        title: 'Message not found',
        description: `Could not find message with ID "${messageId}". The message may not be loaded in the current view.`,
        variant: 'destructive',
      })
    }
  }

  // Get the message for the modal
  const selectedMessage = messageViewModal
    ? messages.find(m => m.message_id === messageViewModal.messageId) || null
    : null

  useIDEKeyboardShortcuts({
    isMac,
    activeFilePath: fileOps.activeFilePath,
    activeFile,
    isExecuting: exec.isExecuting,
    editorHook,
    saveFile: fileOps.saveFile,
    handleRunFile: exec.handleRunFile,
    setQuickSearchOpen,
    setGlobalSearchOpen,
  })

  return (
    <div
      ref={rootRef}
      className={cn('flex flex-col h-full relative', className)}
      onDragEnter={upload.handleDragEnter}
      onDragLeave={upload.handleDragLeave}
      onDragOver={upload.handleDragOver}
      onDrop={upload.handleDrop}
    >
      {/* Resource usage bars (storage + RAM) */}
      <ResourceBars userId={userId} chatId={projectId} />

      {/* Main content row - file tree + editor */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
      <IDEUploadOverlays
        isDraggingFiles={upload.isDraggingFiles}
        isUploading={upload.isUploading}
        uploadProgress={upload.uploadProgress}
        fileInputRef={upload.fileInputRef}
        onCancelUpload={upload.cancelUpload}
        onFileInputChange={upload.handleFileInputChange}
      />

      {/* Mobile Explorer Sheet */}
      {isMobile && (
        <MobileFileExplorer
          open={mobileExplorerOpen}
          onOpenChange={setMobileExplorerOpen}
          fileTreeHook={fileTreeHook}
          gitModifiedFiles={gitModifiedFiles}
          openFile={fileOps.openFile}
          setNewItemDialog={fileOps.setNewItemDialog}
          setRenameDialog={fileOps.setRenameDialog}
          setRenameName={fileOps.setRenameName}
          setDeleteDialog={fileOps.setDeleteDialog}
          showFileDetails={fileOps.showFileDetails}
          downloadFile={fileOps.downloadFile}
          downloadWorkspace={fileOps.downloadWorkspace}
          handleImportClick={upload.handleImportClick}
          moveItem={fileOps.moveItem}
        />
      )}

      {/* Desktop File Tree Panel */}
      {!isMobile && (
        <FileTreePanel
          fileTree={fileTreeHook.fileTree}
          isLoadingTree={fileTreeHook.isLoadingTree}
          selectedPath={fileTreeHook.selectedPath}
          isSidebarCollapsed={isSidebarCollapsed}
          sidebarWidth={sidebar.sidebarWidth}
          isResizing={sidebar.isResizing}
          showHiddenFiles={fileTreeHook.showHiddenFiles}
          modifiedFilePaths={gitModifiedFiles}
          onSelectPath={fileTreeHook.setSelectedPath}
          onToggleDirectory={fileTreeHook.toggleDirectory}
          onOpenFile={fileOps.openFile}
          onNewFile={(parentPath) => fileOps.setNewItemDialog({ open: true, type: 'file', parentPath })}
          onNewFolder={(parentPath) => fileOps.setNewItemDialog({ open: true, type: 'folder', parentPath })}
          onRename={(path, oldName) => {
            fileOps.setRenameDialog({ open: true, path, oldName })
            fileOps.setRenameName(oldName)
          }}
          onDelete={(path) => fileOps.setDeleteDialog({ open: true, path })}
          onShowDetails={fileOps.showFileDetails}
          onDownload={fileOps.downloadFile}
          onDownloadWorkspace={fileOps.downloadWorkspace}
          onImport={upload.handleImportClick}
          onMove={fileOps.moveItem}
          onToggleSidebar={setIsSidebarCollapsed}
          onToggleShowHiddenFiles={() => {
            fileTreeHook.setShowHiddenFiles(!fileTreeHook.showHiddenFiles)
            setTimeout(() => fileTreeHook.loadFileTree(), 0)
          }}
          onStartResize={() => sidebar.setIsResizing(true)}
          getParentPathForNewItem={fileTreeHook.getParentPathForNewItem}
        />
      )}

      {/* Main Editor Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header bar - different for mobile vs desktop */}
        {isMobile ? (
          <div className="flex items-center gap-2 px-2 py-1.5 border-b border-border/50 bg-background">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setMobileExplorerOpen(true)}
              className="h-8 px-2"
            >
              <FolderOpen className="h-4 w-4 mr-1.5" />
              <span className="text-xs">Explorer</span>
            </Button>
            {activeFile && (
              <div className="flex-1 min-w-0 truncate text-xs text-muted-foreground">
                {activeFile.path}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/50 bg-muted/20">
            {/* Keyboard shortcuts */}
            <KeyboardShortcuts
              shortcuts={[
                { ...platformShortcuts.findFiles, action: () => setQuickSearchOpen(true) },
                { ...platformShortcuts.save, action: () => fileOps.activeFilePath && fileOps.saveFile(fileOps.activeFilePath) },
                { ...platformShortcuts.run, action: exec.handleRunFile },
              ]}
            />
            {/* Right side buttons */}
            <div className="flex items-center gap-2">
              {/* Terminal toggle */}
              <Button
                variant={bottomPanelOpen && bottomPanelTab === 'terminal' ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => {
                  if (bottomPanelOpen && bottomPanelTab === 'terminal') {
                    setBottomPanelOpen(false)
                  } else {
                    setBottomPanelOpen(true)
                    setBottomPanelTab('terminal')
                  }
                }}
                className="h-7 px-2 gap-1.5"
              >
                <Terminal className="h-3.5 w-3.5" />
                <span className="text-xs">Terminal</span>
              </Button>
              {/* Quick search button */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setQuickSearchOpen(true)}
                className="h-7 px-2 gap-1.5"
              >
                <Search className="h-3.5 w-3.5" />
                <span className="text-xs">Go to File</span>
              </Button>
            </div>
          </div>
        )}

        {/* Tabs */}
        <EditorTabs
          openFiles={fileOps.openFiles}
          activeFilePath={fileOps.activeFilePath}
          activeFile={activeFile}
          isExecuting={exec.isExecuting}
          viewMode={viewMode}
          onReorder={fileOps.setOpenFiles}
          onSelectFile={(path) => {
            fileOps.setActiveFilePath(path)
            fileTreeHook.setSelectedPath(path)
          }}
          onCloseFile={fileOps.closeFile}
          onSaveFile={fileOps.saveFile}
          onRunFile={exec.handleRunFile}
          onAbortExecution={exec.handleAbort}
          onViewModeChange={setViewMode}
        />

        {/* Breadcrumbs - desktop only */}
        {!isMobile && activeFile && (
          <Breadcrumbs
            filePath={activeFile.path}
            onNavigate={(path) => {
              // Navigate to folder in file tree
              fileTreeHook.setSelectedPath(path)
            }}
          />
        )}

        {/* Editor */}
        <div className={cn(
          "flex-1 flex flex-col overflow-hidden min-w-0 relative",
          isMobile ? "p-2 pt-0" : "p-4 pt-0"
        )}>
          {/* Always render Editor to prevent Monaco unmount/remount issues */}
          <div className={cn(
                "group relative flex-1 overflow-hidden rounded-xl border border-slate-800 transition-colors duration-200 min-w-0",
                activeFile && !exec.result && "hover:border-slate-700"
              )}
              style={{ visibility: (activeFile || preview.previewPort != null) ? 'visible' : 'hidden', position: (activeFile || preview.previewPort != null) ? 'relative' : 'absolute', width: '100%', height: '100%' }}
              >
                {/* Action buttons - appear on hover like CodeBlock (only in code mode) */}
                {activeFile && viewMode === 'code' && (
                  <div className="absolute top-4 right-4 z-10 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => fileOps.saveFile(activeFile.path)}
                      disabled={!activeFile.isDirty}
                      className="bg-slate-800/95 hover:bg-slate-700 border-slate-600 text-slate-200 hover:text-white transition-all duration-200 pointer-events-auto focus:outline-none focus:ring-2 focus:ring-accent-brand/50 active:scale-95"
                    >
                      Save
                    </Button>
                    {getExecutableLanguage(activeFile.path) && (
                      !exec.isExecuting ? (
                        <Button
                          size="sm"
                          onClick={exec.handleRunFile}
                          className="gap-1.5 bg-accent-brand/90 hover:bg-accent-brand text-slate-900 hover:text-slate-950 font-medium transition-all duration-200 pointer-events-auto focus:outline-none focus:ring-2 focus:ring-accent-brand/50 active:scale-95 shadow-lg"
                        >
                          <Play className="h-3.5 w-3.5" />
                          Run
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={exec.handleAbort}
                          className="gap-1.5 pointer-events-auto transition-all duration-200 active:scale-95 shadow-lg"
                        >
                          <StopCircle className="h-3.5 w-3.5" />
                          Stop
                        </Button>
                      )
                    )}
                  </div>
                )}

                <SplitView
                  viewMode={preview.previewPort != null ? 'split' : (activeFile ? viewMode : 'code')}
                  onResizeEnd={() => editorHook.forceLayout()}
                  codeView={
                    <Editor
                      height="100%"
                      onMount={editorMount.handleEditorDidMount}
                      theme={`custom-${codeThemeId}`}
                      options={{
                        minimap: { enabled: true },
                        fontSize: 14,
                        fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', ui-monospace, monospace",
                        fontLigatures: true,
                        lineNumbers: 'on',
                        lineHeight: 24,
                        letterSpacing: 0.5,
                        roundedSelection: false,
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        tabSize: 2,
                        wordWrap: 'off',
                        scrollbar: {
                          horizontal: 'visible',
                          vertical: 'visible',
                          horizontalScrollbarSize: 10,
                          verticalScrollbarSize: 10,
                        },
                        cursorBlinking: 'smooth',
                        cursorSmoothCaretAnimation: 'on',
                        smoothScrolling: true,
                        padding: { top: 16, bottom: 16 },
                      }}
                    />
                  }
                  previewView={
                    preview.previewPort != null && userId ? (
                      <div className="h-full flex flex-col">
                        <div className="flex items-center justify-between px-3 py-1.5 bg-muted/30 border-b border-border/50 shrink-0">
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Globe className="h-3.5 w-3.5" />
                            <span className="font-mono">localhost:{preview.previewPort}</span>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[11px]"
                            onClick={() => preview.setPreviewPort(null)}
                          >
                            <X className="h-3 w-3 mr-1" />
                            Close
                          </Button>
                        </div>
                        {preview.previewTokenLoading || !preview.previewToken ? (
                          <div className="flex-1 flex items-center justify-center">
                            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                          </div>
                        ) : (
                          <iframe
                            src={getPreviewUrl(userId, preview.previewPort, preview.previewToken)}
                            className="flex-1 w-full border-0 bg-white"
                            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                            title={`Preview port ${preview.previewPort}`}
                          />
                        )}
                      </div>
                    ) : activeFile ? (
                      <FilePreview
                        fileName={activeFile.name}
                        filePath={activeFile.path}
                        content={activeFile.content}
                        language={activeFile.language}
                        userId={userId}
                        projectId={projectId}
                      />
                    ) : <div />
                  }
                />
              </div>

              {/* Restoring overlay */}
              {fileTreeHook.isRestoring && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-20">
                  <div className="text-center space-y-3">
                    <Loader2 className="h-8 w-8 mx-auto animate-spin text-primary" />
                    <p className="text-sm text-muted-foreground">Restoring workspace files...</p>
                  </div>
                </div>
              )}

              {/* Empty state overlay */}
              {!activeFile && !fileTreeHook.isRestoring && preview.previewPort == null && (
                <div className="absolute inset-0 flex items-center justify-center text-muted-foreground bg-background">
                  <div className="text-center space-y-3">
                    <FileCode className="h-12 w-12 mx-auto text-muted-foreground/50" />
                    <p className="text-sm text-muted-foreground">No file selected</p>
                    <p className="text-xs text-muted-foreground/70">
                      {isMobile ? 'Tap the button below to browse files' : 'Open a file from the explorer to start editing'}
                    </p>
                    {isMobile && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setMobileExplorerOpen(true)}
                        className="mt-2"
                      >
                        <FolderOpen className="h-4 w-4 mr-2" />
                        Open Explorer
                      </Button>
                    )}
                  </div>
                </div>
              )}

        </div>

        {/* Status Bar - desktop only */}
        {!isMobile && activeFile && (
          <StatusBar
            language={activeFile.language || 'Plain Text'}
            lineCount={activeFile.content?.split('\n').length || 0}
            cursorLine={editorMount.cursorPosition.line}
            cursorColumn={editorMount.cursorPosition.column}
            selectedText={editorMount.selectedTextLength}
          />
        )}
      </div>
      </div>
      {/* End of main content row */}

      {/* Bottom Panel (Output + Terminal + Git) - desktop only, spans full width */}
      {!isMobile && (
        <BottomPanel
          open={bottomPanelOpen}
          onClose={() => setBottomPanelOpen(false)}
          activeTab={bottomPanelTab}
          onTabChange={setBottomPanelTab}
          height={bottomPanelHeight}
          maxHeight={containerHeight > 0 ? containerHeight - 50 : undefined}
          onHeightChange={setBottomPanelHeight}
          result={exec.result}
          onClearOutput={() => exec.setResult(null)}
          userId={userId}
          // Use projectId for code sessions, otherwise original IDs
          conversationId={mode === 'code' ? projectId : conversationId}
          chatId={mode === 'code' ? projectId : chatId}
          mode={mode}
          // Git props (for code sessions)
          gitModifiedFiles={gitModifiedFiles}
          gitCurrentBranch={gitCurrentBranch}
          // Ports
          onPreviewPort={(port) => preview.setPreviewPort(port)}
        />
      )}

      {/* Dialogs */}
      <FileDialogs
        newItemDialog={fileOps.newItemDialog}
        newItemName={fileOps.newItemName}
        onNewItemNameChange={fileOps.setNewItemName}
        onCreateNewItem={fileOps.createNewItem}
        onCancelNewItem={() => {
          fileOps.setNewItemDialog(null)
          fileOps.setNewItemName('')
        }}
        deleteDialog={fileOps.deleteDialog}
        onConfirmDelete={fileOps.deleteItem}
        onCancelDelete={() => fileOps.setDeleteDialog(null)}
        renameDialog={fileOps.renameDialog}
        renameName={fileOps.renameName}
        onRenameNameChange={fileOps.setRenameName}
        onConfirmRename={fileOps.renameItem}
        onCancelRename={() => {
          fileOps.setRenameDialog(null)
          fileOps.setRenameName('')
        }}
        closeFileDialog={fileOps.closeFileDialog}
        onConfirmCloseFile={() => {
          if (fileOps.closeFileDialog) {
            fileOps.performCloseFile(fileOps.closeFileDialog.path)
            fileOps.setCloseFileDialog(null)
          }
        }}
        onCancelCloseFile={() => fileOps.setCloseFileDialog(null)}
      />

      {/* File Details Modal */}
      {fileOps.fileDetailsModal && (
        <FileDetailsModal
          open={fileOps.fileDetailsModal.open}
          onOpenChange={(open) => {
            if (!open) {
              fileOps.setFileDetailsModal(null)
            }
          }}
          filePath={fileOps.fileDetailsModal.path}
          fileName={fileOps.fileDetailsModal.name}
          userId={userId}
          conversationId={conversationId}
          chatId={chatId}
          onNavigateToMessage={handleNavigateToMessage}
        />
      )}

      {/* Message View Modal */}
      <MessageViewModal
        open={messageViewModal?.open || false}
        onOpenChange={(open) => {
          if (!open) {
            setMessageViewModal(null)
          }
        }}
        message={selectedMessage}
        isLoading={false}
      />

      {/* Quick File Search */}
      <QuickFileSearch
        open={quickSearchOpen}
        onOpenChange={setQuickSearchOpen}
        fileTree={fileTreeHook.fileTree}
        recentFiles={fileOps.recentFilePaths}
        onSelectFile={fileOps.openFile}
      />

      {/* Global Search */}
      <GlobalSearch
        open={globalSearchOpen}
        onOpenChange={setGlobalSearchOpen}
        fileTree={fileTreeHook.fileTree}
        userId={userId}
        projectId={projectId}
        onSelectFile={(path, name, line) => {
          fileOps.openFile(path, name)
          // Jump to line if specified
          if (line && editorHook.editorRef?.current) {
            setTimeout(() => {
              const editor = editorHook.editorRef?.current
              if (editor) {
                editor.revealLineInCenter(line)
                editor.setPosition({ lineNumber: line, column: 1 })
                editor.focus()
              }
            }, 100)
          }
        }}
      />
    </div>
  )
}
