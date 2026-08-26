/**
 * Preview state for attachments surfaced in a chat: the image gallery
 * lightbox, the "all attachments" modal, the text-file viewer, and the PDF
 * viewer. Also owns loading assets from storage into blob URLs (auth
 * required) and revoking them on unmount.
 */
import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { assetsAPI } from '@/api/assets'
import type { Attachment, FileAttachment } from '../types'

interface PreviewFile {
  name: string
  size: number
  content: string
}

export function useAttachmentPreviews() {
  // Image gallery state
  const [imageGalleryOpen, setImageGalleryOpen] = useState(false)
  const [galleryImages, setGalleryImages] = useState<{ src: string; alt: string }[]>([])
  const [gallerySelectedIndex, setGallerySelectedIndex] = useState(0)

  // All attachments modal state
  const [isAllAttachmentsOpen, setIsAllAttachmentsOpen] = useState(false)
  const [allAttachments, setAllAttachments] = useState<Attachment[]>([])

  // File preview modal state
  const [isFilePreviewOpen, setIsFilePreviewOpen] = useState(false)
  const [previewFile, setPreviewFile] = useState<PreviewFile | null>(null)
  const [loadingFileId, setLoadingFileId] = useState<string | null>(null)
  // PDF preview modal state
  const [isPdfOpen, setIsPdfOpen] = useState(false)
  const [pdfSrc, setPdfSrc] = useState('')
  const [pdfName, setPdfName] = useState('')
  // Blob URL loading for images/PDFs from asset storage (auth required)
  const [loadedBlobUrls, setLoadedBlobUrls] = useState<Record<string, string>>({})
  const [loadingAssetIds, setLoadingAssetIds] = useState<Set<string>>(new Set())

  // Load asset from storage via API (includes auth headers) and return blob URL
  const loadAssetAsBlobUrl = useCallback(async (assetId: string): Promise<string | null> => {
    if (loadedBlobUrls[assetId]) return loadedBlobUrls[assetId]
    if (loadingAssetIds.has(assetId)) return null

    setLoadingAssetIds(prev => new Set(prev).add(assetId))
    try {
      const blob = await assetsAPI.download(assetId)
      if (blob) {
        const blobUrl = URL.createObjectURL(blob)
        setLoadedBlobUrls(prev => ({ ...prev, [assetId]: blobUrl }))
        return blobUrl
      }
      return null
    } catch (error) {
      console.error('[ImmersiveChatView] Failed to load asset:', assetId, error)
      return null
    } finally {
      setLoadingAssetIds(prev => {
        const next = new Set(prev)
        next.delete(assetId)
        return next
      })
    }
  }, [loadedBlobUrls, loadingAssetIds])

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(loadedBlobUrls).forEach(url => URL.revokeObjectURL(url))
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleOpenImageGallery = useCallback((images: { src: string; alt: string }[], selectedIndex: number) => {
    setGalleryImages(images)
    setGallerySelectedIndex(selectedIndex)
    setImageGalleryOpen(true)
  }, [])

  // PDF preview handler
  const handleOpenPdf = useCallback((src: string, name: string) => {
    setPdfSrc(src)
    setPdfName(name)
    setIsPdfOpen(true)
  }, [])

  const handleOpenTextFile = useCallback(async (file: FileAttachment) => {
    const fileName = file.file?.name || 'file'
    const fileSize = file.file?.size || 0

    // If we have textContent cached, show modal directly
    if (file.textContent) {
      setPreviewFile({ name: fileName, size: fileSize, content: file.textContent })
      setIsFilePreviewOpen(true)
      return
    }

    // If we have an assetId (after reload), fetch the content
    if (file.assetId) {
      setLoadingFileId(file.id)
      try {
        const blob = await assetsAPI.download(file.assetId)
        if (blob) {
          const content = await blob.text()
          setPreviewFile({ name: fileName, size: fileSize, content })
          setIsFilePreviewOpen(true)
        } else {
          toast.error('Failed to load file content')
        }
      } catch (error) {
        console.error('Failed to fetch file content:', error)
        toast.error('Failed to load file content')
      } finally {
        setLoadingFileId(null)
      }
      return
    }

    toast.error('File content not available')
  }, [])

  const handleOpenAllAttachments = useCallback((attachments: Attachment[]) => {
    // Open the all attachments modal to show all attachment types
    setAllAttachments(attachments)
    setIsAllAttachmentsOpen(true)
  }, [])

  return {
    imageGalleryOpen,
    setImageGalleryOpen,
    galleryImages,
    gallerySelectedIndex,
    setGallerySelectedIndex,
    isAllAttachmentsOpen,
    setIsAllAttachmentsOpen,
    allAttachments,
    isFilePreviewOpen,
    setIsFilePreviewOpen,
    previewFile,
    loadingFileId,
    isPdfOpen,
    setIsPdfOpen,
    pdfSrc,
    pdfName,
    loadedBlobUrls,
    loadingAssetIds,
    loadAssetAsBlobUrl,
    handleOpenImageGallery,
    handleOpenPdf,
    handleOpenTextFile,
    handleOpenAllAttachments,
  }
}
