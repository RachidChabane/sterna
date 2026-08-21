/**
 * Image utility functions for handling image attachments
 */

const MAX_IMAGE_SIZE_MB = 5
const MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
const SUPPORTED_FORMATS = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif', 'image/svg+xml']

export interface ImageValidationResult {
  valid: boolean
  error?: string
}

/**
 * Validate an image file
 */
export function validateImage(file: File): ImageValidationResult {
  // Check if file is an image
  if (!file.type.startsWith('image/')) {
    return {
      valid: false,
      error: 'File must be an image'
    }
  }

  // Check if format is supported
  if (!SUPPORTED_FORMATS.includes(file.type)) {
    return {
      valid: false,
      error: `Unsupported image format. Supported formats: PNG, JPEG, WebP, GIF, SVG`
    }
  }

  // Check file size
  if (file.size > MAX_IMAGE_SIZE_BYTES) {
    return {
      valid: false,
      error: `Image size must be less than ${MAX_IMAGE_SIZE_MB}MB`
    }
  }

  return { valid: true }
}

/**
 * Convert an image file to base64 data URL
 */
export function convertImageToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = () => {
      const result = reader.result as string
      resolve(result)
    }

    reader.onerror = () => {
      reject(new Error('Failed to read image file'))
    }

    reader.readAsDataURL(file)
  })
}

/**
 * Create a preview URL for an image file
 */
export function createImagePreview(file: File): string {
  return URL.createObjectURL(file)
}

/**
 * Revoke a preview URL to free memory
 */
export function revokeImagePreview(url: string): void {
  URL.revokeObjectURL(url)
}

/**
 * Get a human-readable file size string
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
