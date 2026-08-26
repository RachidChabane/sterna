/**
 * Attachment viewer state for ChatPanel: the image gallery, PDF preview,
 * text-file preview, and "all attachments" modal. Owns the raw setters
 * (consumed directly by AttachmentModals' callback props, which intentionally
 * update a narrower slice of state than the open* handlers below) as well as
 * the open* handlers used from message actions and the chat context.
 */
import { useCallback, useState } from 'react'
import { assetsAPI } from '@/api/assets'
import type { useToast } from '@/hooks/use-toast'
import type { Attachment, FileAttachment } from '../types'

type ToastFn = ReturnType<typeof useToast>['toast']

export function useAttachmentViewerState(toast: ToastFn) {
  const [isGalleryOpen, setIsGalleryOpen] = useState(false)
  const [galleryImages, setGalleryImages] = useState<{ src: string; alt: string }[]>([])
  const [selectedImageIndex, setSelectedImageIndex] = useState<number | null>(null)
  const [galleryOpenedFromAttachments, setGalleryOpenedFromAttachments] = useState(false)
  const [isPdfOpen, setIsPdfOpen] = useState(false)
  const [pdfSrc, setPdfSrc] = useState<string>("")
  const [pdfName, setPdfName] = useState<string>("")
  const [isAllAttachmentsOpen, setIsAllAttachmentsOpen] = useState(false)
  const [allAttachments, setAllAttachments] = useState<Attachment[]>([])
  const [selectedAllImage, setSelectedAllImage] = useState<{ src: string; alt: string } | null>(null)
  const [selectedFile, setSelectedFile] = useState<FileAttachment | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [fetchedFileContent, setFetchedFileContent] = useState<string | null>(null)

  const handleOpenImageGallery = useCallback((images: { src: string; alt: string }[], selectedIndex: number, fromAttachments: boolean) => {
    setGalleryImages(images)
    setSelectedImageIndex(selectedIndex)
    setSelectedAllImage(images[selectedIndex])
    setIsGalleryOpen(true)
    setGalleryOpenedFromAttachments(fromAttachments)
  }, [])

  const handleOpenPdf = useCallback((src: string, name: string) => {
    setPdfSrc(src)
    setPdfName(name)
    setIsPdfOpen(true)
  }, [])

  const handleOpenTextFile = useCallback(async (file: FileAttachment) => {
    const fileName = file.file?.name || 'file'

    // If we have textContent cached, show modal directly
    if (file.textContent) {
      setFetchedFileContent(null) // Clear any previously fetched content
      setSelectedFile(file)
      setIsModalOpen(true)
      return
    }

    // If we have an assetId (after reload), fetch the content
    const assetId = file.assetId
    if (assetId) {
      try {
        const blob = await assetsAPI.download(assetId)
        if (blob) {
          const content = await blob.text()
          setFetchedFileContent(content)
          setSelectedFile(file)
          setIsModalOpen(true)
        } else {
          toast({
            title: 'Failed to load file',
            description: `Could not load content for ${fileName}`,
            variant: 'destructive'
          })
        }
      } catch (error) {
        console.error('Failed to fetch file content:', error)
        toast({
          title: 'Failed to load file',
          description: `Could not load content for ${fileName}`,
          variant: 'destructive'
        })
      }
      return
    }

    toast({
      title: 'File content not available',
      description: `${fileName} has no content to display`,
      variant: 'destructive'
    })
  }, [toast])

  const handleOpenAllAttachments = useCallback((atts: Attachment[]) => {
    setAllAttachments(atts)
    setIsAllAttachmentsOpen(true)
  }, [])

  return {
    isGalleryOpen, setIsGalleryOpen,
    galleryImages, setGalleryImages,
    selectedImageIndex, setSelectedImageIndex,
    galleryOpenedFromAttachments, setGalleryOpenedFromAttachments,
    isPdfOpen, setIsPdfOpen,
    pdfSrc, setPdfSrc,
    pdfName, setPdfName,
    isAllAttachmentsOpen, setIsAllAttachmentsOpen,
    allAttachments, setAllAttachments,
    selectedAllImage, setSelectedAllImage,
    selectedFile, setSelectedFile,
    isModalOpen, setIsModalOpen,
    fetchedFileContent, setFetchedFileContent,
    handleOpenImageGallery,
    handleOpenPdf,
    handleOpenTextFile,
    handleOpenAllAttachments,
  }
}
