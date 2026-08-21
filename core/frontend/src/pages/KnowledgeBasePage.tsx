/**
 * Knowledge Base Page
 *
 * Provides UI for managing personal knowledge base:
 * - Document upload (drag & drop)
 * - Document list with status
 * - Search interface
 * - Settings panel
 */

import { useEffect, useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import {
  Upload,
  Search,
  Trash2,
  RefreshCw,
  FileText,
  FileCode,
  FileSpreadsheet,
  FileType,
  Globe,
  AlertCircle,
  CheckCircle,
  Loader2,
  Settings2,
  HardDrive,
  X,
  MoreVertical,
  Plus,
  FolderOpen,
  MessageSquare,
} from 'lucide-react'

import { useKnowledgeStore } from '@/store/knowledgeStore'
import { useNavigationStore } from '@/store/navigationStore'
import { knowledgeApi } from '@/api/knowledge'
import { FilePreviewModal } from '@/components/models/FilePreviewModal'
import { PdfPreviewModal } from '@/components/models/PdfPreviewModal'
import { validateFiles } from '@/utils/fileSecurityValidation'
import { useToast } from '@/hooks/use-toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { TypeBadge, getTypeIconColor, getTypeIconBg } from '@/lib/type-badges'
import type { KnowledgeDocument, DocumentStatus, SearchResult } from '@/api/knowledge'

// Accepted file extensions
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.csv', '.html', '.htm', '.json']

// Custom file validator (avoids attr-accept compatibility issues)
const fileValidator = (file: File) => {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase()
  if (!ACCEPTED_EXTENSIONS.includes(ext)) {
    return {
      code: 'file-invalid-type',
      message: `File type not supported. Accepted: ${ACCEPTED_EXTENSIONS.join(', ')}`,
    }
  }
  return null
}

// Status configuration
const STATUS_CONFIG: Record<DocumentStatus, {
  icon: typeof Loader2
  label: string
  animate: boolean
}> = {
  pending: { icon: Loader2, label: 'Pending', animate: true },
  processing: { icon: Loader2, label: 'Processing', animate: true },
  indexing: { icon: Loader2, label: 'Indexing', animate: true },
  ready: { icon: CheckCircle, label: 'Ready', animate: false },
  failed: { icon: AlertCircle, label: 'Failed', animate: false },
}


export default function KnowledgeBasePage() {
  const { toast } = useToast()
  const { openMobileSidebar } = useNavigationStore()
  const {
    settings,
    documents,
    documentsLoading,
    uploadProgress,
    searchResults,
    searchLoading,
    fetchSettings,
    updateSettings,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
    deleteDocuments,
    reprocessDocument,
    search,
    clearSearch,
  } = useKnowledgeStore()

  // Local state
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(new Set())
  const [showSettings, setShowSettings] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [documentToDelete, setDocumentToDelete] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'documents' | 'search'>('documents')
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  const [filterByConversation, setFilterByConversation] = useState(false)

  // Filter documents by conversation tag if filter is active
  const filteredDocuments = filterByConversation
    ? documents.filter(doc => doc.tags?.includes('conversation'))
    : documents

  // Count of conversations in knowledge base
  const conversationCount = documents.filter(doc => doc.tags?.includes('conversation')).length

  // Preview state
  const [previewDoc, setPreviewDoc] = useState<KnowledgeDocument | null>(null)
  const [previewContent, setPreviewContent] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)

  // Fetch data on mount
  useEffect(() => {
    fetchSettings()
    fetchDocuments()
  }, [fetchSettings, fetchDocuments])

  // Dropzone configuration with security validation
  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setShowUploadDialog(false)

      // Validate files using magic byte detection (50MB limit for knowledge base)
      const validation = await validateFiles(acceptedFiles, 50)

      // Show warnings for blocked files (security issues)
      for (const { file, reason } of validation.blockedFiles) {
        toast({
          title: 'File Blocked',
          description: `${file.name}: ${reason}`,
          variant: 'destructive',
        })
      }

      // Show warnings for invalid files
      for (const { file, reason } of validation.invalidFiles) {
        toast({
          title: 'Invalid File',
          description: `${file.name}: ${reason}`,
          variant: 'destructive',
        })
      }

      // Show type mismatch warnings (non-blocking)
      for (const { file, message } of validation.warnings) {
        toast({
          title: 'Warning',
          description: `${file.name}: ${message}`,
        })
      }

      // Upload only valid files
      for (const file of validation.validFiles) {
        await uploadDocument(file)
      }
    },
    [uploadDocument, toast]
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    validator: fileValidator,
    maxSize: 50 * 1024 * 1024, // 50MB
  })

  // Handle search
  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    await search(searchQuery)
  }

  // Handle document selection
  const toggleDocumentSelection = (id: string) => {
    setSelectedDocuments((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const selectAllDocuments = () => {
    if (selectedDocuments.size === filteredDocuments.length) {
      setSelectedDocuments(new Set())
    } else {
      setSelectedDocuments(new Set(filteredDocuments.map((d) => d.id)))
    }
  }

  // Handle delete
  const handleDeleteSelected = async () => {
    if (selectedDocuments.size === 0) return
    await deleteDocuments(Array.from(selectedDocuments))
    setSelectedDocuments(new Set())
  }

  const handleDeleteSingle = async () => {
    if (!documentToDelete) return
    await deleteDocument(documentToDelete)
    setDocumentToDelete(null)
    setDeleteConfirmOpen(false)
  }

  // Handle document preview click
  const handleDocumentClick = async (doc: KnowledgeDocument) => {
    if (doc.status !== 'ready') return

    setPreviewLoading(true)
    setPreviewDoc(doc)

    try {
      const blob = await knowledgeApi.downloadDocument(doc.id)
      if (!blob) throw new Error('Download failed')

      if (doc.document_type === 'pdf') {
        // Convert to base64 data URL for PDF viewer
        const reader = new FileReader()
        reader.onload = () => {
          setPreviewContent(reader.result as string)
          setPreviewLoading(false)
        }
        reader.onerror = () => {
          console.error('Failed to read PDF as data URL')
          setPreviewDoc(null)
          setPreviewLoading(false)
        }
        reader.readAsDataURL(blob)
      } else {
        // Text content for FilePreviewModal
        const text = await blob.text()
        setPreviewContent(text)
        setPreviewLoading(false)
      }
    } catch (error) {
      console.error('Failed to load document:', error)
      setPreviewDoc(null)
      setPreviewLoading(false)
    }
  }

  // Close preview modal
  const closePreview = () => {
    setPreviewDoc(null)
    setPreviewContent('')
  }

  // Render document status - small, subtle badges matching app style
  const renderStatus = (status: DocumentStatus, errorMessage?: string) => {
    const config = STATUS_CONFIG[status]
    const Icon = config.icon

    // Status-specific badge styling (subtle backgrounds, muted text)
    const statusStyles: Record<DocumentStatus, string> = {
      pending: 'bg-amber-500/10 text-amber-600/70',
      processing: 'bg-blue-500/10 text-blue-600/70',
      indexing: 'bg-purple-500/10 text-purple-600/70',
      ready: 'bg-emerald-500/10 text-emerald-600/70',
      failed: 'bg-red-500/10 text-red-600/70',
    }

    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={cn(
              'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
              statusStyles[status]
            )}>
              <Icon className={cn('h-2.5 w-2.5', config.animate && 'animate-spin')} />
              {config.label}
            </span>
          </TooltipTrigger>
          {status === 'failed' && errorMessage && (
            <TooltipContent>
              <p className="max-w-xs text-sm">{errorMessage}</p>
            </TooltipContent>
          )}
        </Tooltip>
      </TooltipProvider>
    )
  }

  // Render document card
  const renderDocument = (doc: KnowledgeDocument) => {
    const isSelected = selectedDocuments.has(doc.id)
    const isProcessing = doc.status === 'processing' || doc.status === 'indexing' || doc.status === 'pending'

    return (
      <div
        key={doc.id}
        onClick={() => handleDocumentClick(doc)}
        className={cn(
          'group relative rounded-xl border transition-all duration-200 overflow-hidden',
          doc.status === 'ready' ? 'cursor-pointer' : 'cursor-not-allowed',
          isSelected
            ? 'bg-accent-brand/5 border-accent-brand ring-1 ring-accent-brand/20'
            : 'bg-card/30 border-border/40 hover:bg-card/50 hover:border-border/60'
        )}
      >
        {/* Selection checkbox - top left corner */}
        <div className="absolute top-3 left-2 sm:left-3 z-10" onClick={(e) => e.stopPropagation()}>
          <Checkbox
            checked={isSelected}
            onCheckedChange={() => toggleDocumentSelection(doc.id)}
            className={cn(
              'transition-opacity',
              isSelected ? 'opacity-100' : 'sm:opacity-0 sm:group-hover:opacity-100'
            )}
          />
        </div>

        <div className="p-3 pl-8 sm:p-4 sm:pl-10 min-w-0">
          <div className="min-w-0">
            <div className="flex items-start justify-between gap-2 min-w-0">
              <div className="min-w-0 flex-1">
                <h3 className="font-medium text-foreground text-sm sm:text-base truncate">
                  {doc.filename}
                </h3>
                <div className="flex items-center gap-1.5 sm:gap-2 mt-1.5 flex-wrap">
                  {renderStatus(doc.status, doc.error_message)}
                  <TypeBadge type={doc.document_type} />
                  <span className="text-[10px] text-muted-foreground/60">•</span>
                  <span className="text-[10px] text-muted-foreground/70">
                    {doc.file_size_display}
                  </span>
                </div>
              </div>

              {/* Actions menu */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 flex-shrink-0 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={() => reprocessDocument(doc.id)}
                    disabled={isProcessing}
                  >
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Reprocess
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-destructive"
                    onClick={() => {
                      setDocumentToDelete(doc.id)
                      setDeleteConfirmOpen(true)
                    }}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Stats row */}
            {doc.status === 'ready' && (doc.chunk_count > 0 || doc.page_count) && (
              <div className="flex items-center gap-3 mt-3 pt-3 border-t border-border/30">
                {doc.chunk_count > 0 && (
                  <span className="text-[10px] text-muted-foreground/70">
                    {doc.chunk_count} chunks
                  </span>
                )}
                {doc.chunk_count > 0 && doc.page_count && (
                  <span className="text-[10px] text-muted-foreground/50">•</span>
                )}
                {doc.page_count && (
                  <span className="text-[10px] text-muted-foreground/70">
                    {doc.page_count} pages
                  </span>
                )}
              </div>
            )}

            {/* Tags */}
            {doc.tags.length > 0 && (
              <div className="flex items-center gap-1 mt-2 flex-wrap">
                {doc.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-[9px] font-medium px-1.5 py-0.5 rounded bg-muted/40 text-muted-foreground"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Processing overlay */}
        {isProcessing && (
          <div className="absolute inset-0 bg-background/50 backdrop-blur-[1px] rounded-xl flex items-center justify-center">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{STATUS_CONFIG[doc.status].label}...</span>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Get file type icon (color from centralized type-badges)
  const getFileTypeIcon = (docType: string) => {
    switch (docType) {
      case 'pdf': return FileType
      case 'md': case 'txt': return FileText
      case 'csv': return FileSpreadsheet
      case 'json': return FileCode
      case 'html': return Globe
      case 'docx': return FileText
      default: return FileText
    }
  }

  // Render search result
  const renderSearchResult = (result: SearchResult) => {
    const FileIcon = getFileTypeIcon(result.document_type)

    return (
      <Card key={result.chunk_id} className="mb-3 border-border/50 hover:border-border/80 transition-colors">
        <CardContent className="pt-4">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2.5">
              <div className={cn('p-1.5 rounded-md', getTypeIconBg(result.document_type))}>
                <FileIcon className={cn('h-3.5 w-3.5', getTypeIconColor(result.document_type))} />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium leading-tight">{result.document_filename}</span>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <TypeBadge type={result.document_type} />
                  {result.page_number && (
                    <>
                      <span className="text-[10px] text-muted-foreground/50">•</span>
                      <span className="text-[10px] text-muted-foreground">
                        Page {result.page_number}
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <Badge
              variant="secondary"
              className={cn(
                'text-[10px] font-semibold px-2',
                result.similarity_score >= 0.9 ? 'bg-emerald-500/15 text-emerald-600' :
                result.similarity_score >= 0.8 ? 'bg-blue-500/15 text-blue-600' :
                result.similarity_score >= 0.7 ? 'bg-amber-500/15 text-amber-600' :
                'bg-muted text-muted-foreground'
              )}
            >
              {(result.similarity_score * 100).toFixed(0)}% match
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground line-clamp-4 leading-relaxed">{result.content}</p>
        </CardContent>
      </Card>
    )
  }

  // Render settings dialog
  const renderSettingsDialog = () => (
    <Dialog open={showSettings} onOpenChange={setShowSettings}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Knowledge Base Settings</DialogTitle>
          <DialogDescription>
            Configure how your knowledge base works with AI conversations.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Enable/Disable */}
          <div className="flex items-center justify-between">
            <div>
              <Label>Enable Knowledge Base</Label>
              <p className="text-sm text-muted-foreground">
                Allow AI to access your documents
              </p>
            </div>
            <Switch
              checked={settings?.is_enabled ?? true}
              onCheckedChange={(checked) => updateSettings({ is_enabled: checked })}
            />
          </div>

          {/* Similarity Threshold */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Similarity Threshold</Label>
              <span className="text-sm text-muted-foreground">
                {((settings?.similarity_threshold ?? 0.7) * 100).toFixed(0)}%
              </span>
            </div>
            <Slider
              value={[(settings?.similarity_threshold ?? 0.7) * 100]}
              min={50}
              max={95}
              step={5}
              onValueChange={([value]) =>
                updateSettings({ similarity_threshold: value / 100 })
              }
            />
            <p className="text-xs text-muted-foreground">
              Higher values return more relevant but fewer results
            </p>
          </div>

          {/* Max Chunks */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Max Results per Query</Label>
              <span className="text-sm text-muted-foreground">
                {settings?.max_chunks_per_query ?? 5}
              </span>
            </div>
            <Slider
              value={[settings?.max_chunks_per_query ?? 5]}
              min={1}
              max={10}
              step={1}
              onValueChange={([value]) =>
                updateSettings({ max_chunks_per_query: value })
              }
            />
          </div>
        </div>

        <DialogFooter>
          <Button onClick={() => setShowSettings(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )

  // Render upload dialog for mobile
  const renderUploadDialog = () => (
    <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Upload Documents</DialogTitle>
          <DialogDescription>
            Add documents to your knowledge base for AI to reference.
          </DialogDescription>
        </DialogHeader>

        <div
          {...getRootProps()}
          className={cn(
            'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
            isDragActive && !isDragReject && 'border-accent-brand bg-accent-brand/5',
            isDragReject && 'border-destructive bg-destructive/5',
            !isDragActive && 'border-muted-foreground/25 hover:border-accent-brand/50'
          )}
        >
          <input {...getInputProps()} />
          <Upload className="h-10 w-10 mx-auto mb-4 text-muted-foreground" />
          {isDragActive && !isDragReject ? (
            <p className="text-accent-brand">Drop files here...</p>
          ) : isDragReject ? (
            <p className="text-destructive">Some files are not supported</p>
          ) : (
            <>
              <p className="font-medium">Drop files here or tap to upload</p>
              <p className="text-sm text-muted-foreground mt-1">
                PDF, DOCX, TXT, MD, CSV, HTML, JSON (max 50MB)
              </p>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Mobile header */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border/50 sticky top-0 z-40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <button
          onClick={openMobileSidebar}
          className="p-2 -ml-2 text-foreground transition-colors"
        >
          <PremiumMenuIcon size={18} />
        </button>
        <h1 className="text-base font-medium text-foreground">Knowledge Base</h1>
        <button
          onClick={() => setShowSettings(true)}
          className="p-2 -mr-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Settings2 className="h-5 w-5" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Sticky desktop header */}
        <div className="sticky top-0 z-30 bg-background hidden md:block">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 pb-0">
            {/* Title row */}
            <div className="flex items-center justify-between gap-4">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                Knowledge Base
              </h1>
              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="outline"
                  onClick={() => setShowSettings(true)}
                  className="h-9 px-3"
                >
                  <Settings2 className="h-4 w-4 sm:mr-2" />
                  <span className="hidden sm:inline">Settings</span>
                </Button>
                <Button
                  onClick={() => setShowUploadDialog(true)}
                  variant="outline"
                  className="rounded-full h-9 px-4 flex-shrink-0 text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
                >
                  <Upload className="h-4 w-4 mr-2" />
                  Upload
                </Button>
              </div>
            </div>

            {/* Tab navigation */}
            <div className="flex items-center -mb-px mt-5">
              <button
                onClick={() => setActiveTab('documents')}
                className={cn(
                  "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all",
                  activeTab === 'documents'
                    ? "border-accent-brand text-accent-brand"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <FolderOpen className="w-4 h-4" />
                <span>Documents</span>
                {documents.length > 0 && (
                  <span className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded-full font-medium",
                    activeTab === 'documents'
                      ? "bg-accent-brand/15 text-accent-brand"
                      : "bg-muted text-muted-foreground"
                  )}>
                    {documents.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveTab('search')}
                className={cn(
                  "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all",
                  activeTab === 'search'
                    ? "border-accent-brand text-accent-brand"
                    : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
                )}
              >
                <Search className="w-4 h-4" />
                <span>Search</span>
              </button>
            </div>
          </div>
          <div className="border-b border-border/50" />
        </div>

        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8 pb-24 md:pb-8">
          {/* Documents Tab */}
          {activeTab === 'documents' && (
            <>
              {/* Storage Stats (scrollable, top of documents tab) */}
              {settings && (
                <div className="mb-4 p-3 sm:p-4 rounded-xl bg-muted/20 border border-border/40">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <HardDrive className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs sm:text-sm font-medium">Storage Used</span>
                    </div>
                    <span className="text-xs sm:text-sm text-muted-foreground">
                      {settings.storage_used_mb.toFixed(1)} MB / {settings.storage_limit_mb} MB
                    </span>
                  </div>
                  <Progress value={settings.storage_percentage} className="h-1.5 sm:h-2" />
                  <div className="hidden sm:flex items-center justify-between mt-2 text-xs text-muted-foreground">
                    <span>{settings.total_documents} documents</span>
                    <span>{settings.total_chunks} chunks indexed</span>
                  </div>
                </div>
              )}

              {/* Upload Progress */}
              {Object.entries(uploadProgress).length > 0 && (
                <Card className="mb-6 border-border/50">
                  <CardContent className="pt-4">
                    {Object.entries(uploadProgress).map(([fileId, progress]) => (
                      <div key={fileId} className="flex items-center gap-3">
                        <Loader2 className="h-4 w-4 animate-spin text-accent-brand" />
                        <div className="flex-1">
                          <div className="flex items-center justify-between text-sm mb-1">
                            <span>{fileId.split('-')[0]}</span>
                            <span>{progress}%</span>
                          </div>
                          <Progress value={progress} className="h-1" />
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Bulk Actions */}
              {selectedDocuments.size > 0 && (
                <div className="flex items-center gap-3 mb-4 p-3 bg-accent-brand/10 rounded-lg border border-accent-brand/20">
                  <span className="text-sm font-medium text-accent-brand">
                    {selectedDocuments.size} selected
                  </span>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleDeleteSelected}
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedDocuments(new Set())}
                  >
                    Clear
                  </Button>
                </div>
              )}

              {/* Document List */}
              {documentsLoading ? (
                <div className="flex items-center justify-center py-16">
                  <div className="flex flex-col items-center gap-4">
                    <div className="relative">
                      <div className="w-10 h-10 rounded-full border-2 border-accent-brand/20 border-t-accent-brand animate-spin" />
                    </div>
                    <p className="text-sm text-muted-foreground">Loading documents...</p>
                  </div>
                </div>
              ) : filteredDocuments.length === 0 && !filterByConversation ? (
                <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
                  <div className="relative flex flex-col items-center justify-center py-16 px-6">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                      <FileText className="w-7 h-7 text-muted-foreground/50" />
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-2">No documents yet</h3>
                    <p className="text-sm text-muted-foreground max-w-sm text-center mb-6">
                      Upload documents to build your personal knowledge base
                    </p>
                    <Button
                      onClick={() => setShowUploadDialog(true)}
                      variant="outline"
                      className="rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
                    >
                      <Upload className="w-4 h-4 mr-2" />
                      Upload Documents
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Header row */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Checkbox
                        checked={selectedDocuments.size === filteredDocuments.length && filteredDocuments.length > 0}
                        onCheckedChange={selectAllDocuments}
                      />
                      <span className="text-sm text-muted-foreground">
                        {selectedDocuments.size > 0
                          ? `${selectedDocuments.size} of ${filteredDocuments.length} selected`
                          : filterByConversation
                            ? `${filteredDocuments.length} conversation${filteredDocuments.length !== 1 ? 's' : ''}`
                            : `${filteredDocuments.length} document${filteredDocuments.length !== 1 ? 's' : ''}`
                        }
                      </span>
                    </div>

                    {/* Filter toggle */}
                    {conversationCount > 0 && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant={filterByConversation ? 'default' : 'outline'}
                              size="sm"
                              onClick={() => setFilterByConversation(!filterByConversation)}
                              className={cn(
                                'h-8 gap-1.5',
                                filterByConversation && 'bg-accent-brand hover:bg-accent-brand/90'
                              )}
                            >
                              <MessageSquare className="h-3.5 w-3.5" />
                              <span className="hidden sm:inline">Conversations</span>
                              <Badge variant="secondary" className={cn(
                                'ml-1 h-5 px-1.5 text-[10px]',
                                filterByConversation && 'bg-white/20 text-white'
                              )}>
                                {conversationCount}
                              </Badge>
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {filterByConversation ? 'Show all documents' : 'Show only saved conversations'}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                  </div>

                  {/* Empty state when filter active but no conversations */}
                  {filterByConversation && filteredDocuments.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center">
                      <MessageSquare className="h-10 w-10 text-muted-foreground/30 mb-3" />
                      <p className="text-sm text-muted-foreground">No saved conversations</p>
                      <p className="text-xs text-muted-foreground/70 mt-1">
                        Save a chat to your knowledge base to see it here
                      </p>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFilterByConversation(false)}
                        className="mt-4"
                      >
                        Show all documents
                      </Button>
                    </div>
                  ) : (
                    /* Document grid */
                    <div className="grid gap-2 sm:gap-3 sm:grid-cols-2 lg:grid-cols-3">
                      {filteredDocuments.map(renderDocument)}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Search Tab */}
          {activeTab === 'search' && (
            <>
              {/* Search Input */}
              <div className="flex gap-2 mb-6">
                <Input
                  placeholder="Search your knowledge base..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="flex-1"
                />
                <Button onClick={handleSearch} disabled={searchLoading || !searchQuery.trim()}>
                  {searchLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                </Button>
                {searchResults.length > 0 && (
                  <Button variant="ghost" onClick={clearSearch}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>

              {/* Search Results */}
              {searchResults.length > 0 ? (
                <div>
                  <p className="text-sm text-muted-foreground mb-4">
                    Found {searchResults.length} relevant passages
                  </p>
                  {searchResults.map(renderSearchResult)}
                </div>
              ) : searchQuery && !searchLoading ? (
                <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
                  <div className="relative flex flex-col items-center justify-center py-16 px-6">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                      <Search className="w-7 h-7 text-muted-foreground/50" />
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-2">No results found</h3>
                    <p className="text-sm text-muted-foreground max-w-sm text-center">
                      Try a different search term or upload more documents
                    </p>
                  </div>
                </div>
              ) : (
                <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
                  <div className="relative flex flex-col items-center justify-center py-16 px-6">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                      <Search className="w-7 h-7 text-muted-foreground/50" />
                    </div>
                    <h3 className="text-base font-semibold text-foreground mb-2">Search your documents</h3>
                    <p className="text-sm text-muted-foreground max-w-sm text-center">
                      Enter a query to find relevant information from your knowledge base
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Mobile Bottom Navigation */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 z-20 bg-background/95 backdrop-blur-xl border-t border-border/50 safe-area-bottom">
        <div className="flex items-center">
          <button
            onClick={() => setActiveTab('documents')}
            className={cn(
              "flex-1 flex flex-col items-center gap-1 py-3 transition-colors",
              activeTab === 'documents'
                ? "text-accent-brand"
                : "text-muted-foreground"
            )}
          >
            <div className="relative">
              <FolderOpen className="w-5 h-5" />
              {documents.length > 0 && (
                <span className="absolute -top-1 -right-3 text-[10px] min-w-[16px] h-4 px-1 rounded-full bg-accent-brand text-white font-medium flex items-center justify-center">
                  {documents.length}
                </span>
              )}
            </div>
            <span className="text-xs font-medium">Documents</span>
          </button>
          <button
            onClick={() => setActiveTab('search')}
            className={cn(
              "flex-1 flex flex-col items-center gap-1 py-3 transition-colors",
              activeTab === 'search'
                ? "text-accent-brand"
                : "text-muted-foreground"
            )}
          >
            <Search className="w-5 h-5" />
            <span className="text-xs font-medium">Search</span>
          </button>
        </div>
      </div>

      {/* Mobile FAB for Upload */}
      <button
        onClick={() => setShowUploadDialog(true)}
        className="md:hidden fixed bottom-20 right-4 z-20 w-14 h-14 rounded-full bg-accent-brand text-white shadow-lg shadow-accent-brand/25 flex items-center justify-center active:scale-95 transition-transform safe-area-bottom"
        aria-label="Upload Document"
      >
        <Plus className="w-6 h-6" />
      </button>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Document</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this document? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteSingle}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Settings Dialog */}
      {renderSettingsDialog()}

      {/* Upload Dialog for Mobile */}
      {renderUploadDialog()}

      {/* Document Preview Modals */}
      {previewDoc && previewContent && (
        previewDoc.document_type === 'pdf' ? (
          <PdfPreviewModal
            isOpen={true}
            onClose={closePreview}
            pdfSrc={previewContent}
            pdfName={previewDoc.filename}
          />
        ) : (
          <FilePreviewModal
            isOpen={true}
            onClose={closePreview}
            textContent={previewContent}
            fileName={previewDoc.filename}
            fileSize={previewDoc.file_size_bytes}
          />
        )
      )}

      {/* Preview loading overlay */}
      {previewLoading && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-accent-brand" />
            <span className="text-sm text-muted-foreground">Loading document...</span>
          </div>
        </div>
      )}
    </div>
  )
}
