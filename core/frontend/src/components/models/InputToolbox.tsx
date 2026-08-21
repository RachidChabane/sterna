/**
 * InputToolbox Component
 *
 * Provides a toolbar for attaching media (images) to chat messages
 */

import { useRef } from 'react'
import { Button } from '@/components/ui/button'
import { ImagePlus, X } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import { generateUUID } from '@/lib/utils'
import type { ImageAttachment } from './types'
import {
  validateImage,
  convertImageToBase64,
  createImagePreview,
  revokeImagePreview,
  formatFileSize
} from '@/utils/imageUtils'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

interface InputToolboxProps {
  attachedImages: ImageAttachment[]
  onImageAttach: (image: ImageAttachment) => void
  onImageRemove: (imageId: string) => void
  disabled?: boolean
  hasVisionModels: boolean
}

export function InputToolbox({
  attachedImages,
  onImageAttach,
  onImageRemove,
  disabled = false,
  hasVisionModels
}: InputToolboxProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const handleImageSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const file = files[0]

    // Validate image
    const validation = validateImage(file)
    if (!validation.valid) {
      toast({
        title: 'Invalid image',
        description: validation.error,
        variant: 'destructive'
      })
      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      return
    }

    try {
      // Convert to base64
      const base64 = await convertImageToBase64(file)

      // Create preview
      const preview = createImagePreview(file)

      // Create attachment
      const attachment: ImageAttachment = {
        id: generateUUID(),
        type: 'image',
        file,
        preview,
        base64
      }

      onImageAttach(attachment)

      toast({
        title: 'Image attached',
        description: `${file.name} (${formatFileSize(file.size)})`
      })
    } catch (error) {
      toast({
        title: 'Failed to process image',
        description: 'Could not read the image file',
        variant: 'destructive'
      })
    }

    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleRemoveImage = (imageId: string) => {
    const image = attachedImages.find(img => img.id === imageId)
    if (image) {
      // Revoke preview URL to free memory
      revokeImagePreview(image.preview)
      onImageRemove(imageId)
    }
  }

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-block">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={disabled || !hasVisionModels}
                  className="gap-2"
                >
                  <ImagePlus className="h-4 w-4" />
                  Attach Image
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              <p>
                {!hasVisionModels
                  ? 'No models with vision support are selected'
                  : 'Upload an image (PNG, JPEG, WebP, GIF, SVG, max 5MB)'}
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
          onChange={handleImageSelect}
          className="hidden"
        />

        {attachedImages.length > 0 && (
          <span className="text-sm text-muted-foreground">
            {attachedImages.length} image{attachedImages.length > 1 ? 's' : ''} attached
          </span>
        )}
      </div>

      {/* Image Previews */}
      {attachedImages.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {attachedImages.map((image) => (
            <div
              key={image.id}
              className="relative group rounded-lg border border-border overflow-hidden"
              style={{ width: '100px', height: '100px' }}
            >
              <img
                src={image.preview}
                alt={image.file.name}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Button
                  type="button"
                  variant="destructive"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => handleRemoveImage(image.id)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-2 py-1 text-xs text-white truncate">
                {image.file.name}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
