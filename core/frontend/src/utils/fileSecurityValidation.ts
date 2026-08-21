/**
 * File Security Validation Utilities
 *
 * Centralized file validation and security checks using magic byte detection.
 * Prevents malicious files from being uploaded by:
 * - Detecting executables masquerading as other file types
 * - Detecting binary files claiming to be text files
 * - Validating file type matches extension
 *
 * Used across: Chat attachments, IDE uploads, drag & drop, paste handlers
 */

export interface FileTypeDetectionResult {
  mimeType: string
  category: 'image' | 'document' | 'archive' | 'executable' | 'media' | 'unknown'
}

export interface FileValidationResult {
  valid: boolean
  warning?: string
  shouldBlock?: boolean
  detectedType?: FileTypeDetectionResult
}

/**
 * Detect real file type using magic bytes (file signature)
 * Reads the first 16 bytes of the file to identify its true type
 */
export const detectRealFileType = async (file: File): Promise<FileTypeDetectionResult> => {
  return new Promise((resolve) => {
    const reader = new FileReader()

    reader.onload = (e) => {
      const arr = new Uint8Array(e.target?.result as ArrayBuffer).subarray(0, 16)
      let header = ''
      for (let i = 0; i < arr.length && i < 8; i++) {
        header += arr[i].toString(16).padStart(2, '0')
      }

      // Magic bytes signatures (most common)
      const signatures: Record<string, { mime: string; category: FileTypeDetectionResult['category'] }> = {
        // Images
        '89504e47': { mime: 'image/png', category: 'image' },
        'ffd8ffe0': { mime: 'image/jpeg', category: 'image' },
        'ffd8ffe1': { mime: 'image/jpeg', category: 'image' },
        'ffd8ffe2': { mime: 'image/jpeg', category: 'image' },
        'ffd8ffe8': { mime: 'image/jpeg', category: 'image' },
        '47494638': { mime: 'image/gif', category: 'image' },
        '424d': { mime: 'image/bmp', category: 'image' },
        '00000100': { mime: 'image/x-icon', category: 'image' },
        '49492a00': { mime: 'image/tiff', category: 'image' },
        '4d4d002a': { mime: 'image/tiff', category: 'image' },
        '52494646': { mime: 'image/webp', category: 'image' }, // WEBP (also used by WAV, check further)

        // Documents
        '25504446': { mime: 'application/pdf', category: 'document' },
        '504b0304': { mime: 'application/zip', category: 'archive' }, // ZIP, DOCX, XLSX, PPTX, ODT, ODS, ODP
        '504b0506': { mime: 'application/zip', category: 'archive' },
        '504b0708': { mime: 'application/zip', category: 'archive' },
        'd0cf11e0': { mime: 'application/vnd.ms-office', category: 'document' }, // Old Office (DOC, XLS, PPT)
        '7b5c7274': { mime: 'application/rtf', category: 'document' }, // RTF ({\rtf)

        // Archives
        '1f8b': { mime: 'application/gzip', category: 'archive' },
        '526172': { mime: 'application/x-rar', category: 'archive' },
        '377abcaf': { mime: 'application/x-7z-compressed', category: 'archive' },
        '425a68': { mime: 'application/x-bzip2', category: 'archive' },
        '75737461': { mime: 'application/x-tar', category: 'archive' }, // TAR (ustar)

        // Executables - CRITICAL FOR SECURITY
        '4d5a': { mime: 'application/x-msdownload', category: 'executable' }, // .exe, .dll
        '7f454c46': { mime: 'application/x-elf', category: 'executable' }, // Linux executable
        'cafebabe': { mime: 'application/java-vm', category: 'executable' }, // Java class
        'feedface': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS binary
        'cefaedfe': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS binary
        'feedfacf': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS 64-bit
        'cffaedfe': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS 64-bit
        '4d534346': { mime: 'application/vnd.ms-cab-compressed', category: 'executable' }, // CAB installer

        // Media
        '000001ba': { mime: 'video/mpeg', category: 'media' },
        '000001b3': { mime: 'video/mpeg', category: 'media' },
        '66747970': { mime: 'video/mp4', category: 'media' },
        '1a45dfa3': { mime: 'video/webm', category: 'media' }, // WebM/Matroska
        '494433': { mime: 'audio/mpeg', category: 'media' }, // MP3
        'fffb': { mime: 'audio/mpeg', category: 'media' }, // MP3 (no ID3)
        '4f676753': { mime: 'audio/ogg', category: 'media' }, // OGG
      }

      // Check for matches (try different header lengths)
      for (let len = 8; len >= 2; len--) {
        const truncated = header.substring(0, len * 2)
        if (signatures[truncated]) {
          return resolve({
            mimeType: signatures[truncated].mime,
            category: signatures[truncated].category
          })
        }
      }

      resolve({ mimeType: 'application/octet-stream', category: 'unknown' })
    }

    reader.onerror = () => {
      resolve({ mimeType: 'application/octet-stream', category: 'unknown' })
    }

    reader.readAsArrayBuffer(file.slice(0, 16))
  })
}

/**
 * Validate file type matches extension and is not malicious
 * Returns validation result with warnings or blocking flags
 */
export const validateFileType = async (file: File): Promise<FileValidationResult> => {
  const declaredExt = file.name.split('.').pop()?.toLowerCase() || ''
  const realType = await detectRealFileType(file)

  // Define text/code file extensions (should NOT be binary)
  const textExtensions = [
    'txt', 'md', 'py', 'js', 'ts', 'tsx', 'jsx', 'java', 'cpp', 'c', 'h', 'hpp',
    'css', 'scss', 'sass', 'less', 'html', 'htm', 'xml', 'json', 'yaml', 'yml',
    'sh', 'bash', 'zsh', 'fish', 'sql', 'rs', 'go', 'php', 'rb', 'swift', 'kt',
    'cs', 'r', 'scala', 'dart', 'vue', 'svelte', 'astro', 'toml', 'ini', 'cfg',
    'conf', 'env', 'log', 'csv', 'tsv'
  ]

  // Define expected MIME types for common extensions
  const expectedTypes: Record<string, string[]> = {
    // Images
    'png': ['image/png'],
    'jpg': ['image/jpeg'],
    'jpeg': ['image/jpeg'],
    'gif': ['image/gif'],
    'bmp': ['image/bmp'],
    'ico': ['image/x-icon'],
    'tiff': ['image/tiff'],
    'tif': ['image/tiff'],
    'webp': ['image/webp'],
    'svg': ['image/svg+xml'],

    // Documents
    'pdf': ['application/pdf'],
    'rtf': ['application/rtf'],

    // Microsoft Office (modern - ZIP based)
    'xlsx': ['application/zip', 'application/octet-stream'],
    'xlsm': ['application/zip', 'application/octet-stream'],
    'xlsb': ['application/zip', 'application/octet-stream'],
    'docx': ['application/zip', 'application/octet-stream'],
    'docm': ['application/zip', 'application/octet-stream'],
    'pptx': ['application/zip', 'application/octet-stream'],
    'pptm': ['application/zip', 'application/octet-stream'],

    // Microsoft Office (old - Binary)
    'xls': ['application/vnd.ms-office', 'application/octet-stream'],
    'doc': ['application/vnd.ms-office', 'application/octet-stream'],
    'ppt': ['application/vnd.ms-office', 'application/octet-stream'],

    // LibreOffice/OpenOffice (ZIP based)
    'odt': ['application/zip', 'application/octet-stream'],
    'ods': ['application/zip', 'application/octet-stream'],
    'odp': ['application/zip', 'application/octet-stream'],
    'odg': ['application/zip', 'application/octet-stream'],

    // Archives
    'zip': ['application/zip', 'application/octet-stream'],
    'gz': ['application/gzip', 'application/octet-stream'],
    'rar': ['application/x-rar', 'application/octet-stream'],
    '7z': ['application/x-7z-compressed', 'application/octet-stream'],
    'tar': ['application/x-tar', 'application/octet-stream'],
    'bz2': ['application/x-bzip2', 'application/octet-stream'],

    // Media
    'mp3': ['audio/mpeg', 'application/octet-stream'],
    'wav': ['audio/wav', 'application/octet-stream'],
    'ogg': ['audio/ogg', 'application/octet-stream'],
    'mp4': ['video/mp4', 'application/octet-stream'],
    'webm': ['video/webm', 'application/octet-stream'],
    'mpeg': ['video/mpeg', 'application/octet-stream'],
    'mpg': ['video/mpeg', 'application/octet-stream'],
  }

  // CRITICAL: Block executables masquerading as non-executable types
  if (realType.category === 'executable' && !['exe', 'dll', 'so', 'dylib', 'elf', 'class'].includes(declaredExt)) {
    return {
      valid: false,
      warning: `SECURITY WARNING: "${file.name}" appears to be an executable file (.${declaredExt} → ${realType.mimeType})`,
      shouldBlock: true,
      detectedType: realType
    }
  }

  // CRITICAL: Block binary files (images, PDFs, etc.) masquerading as text/code files
  if (textExtensions.includes(declaredExt)) {
    // Check if the real type is a known binary format
    const knownBinaryTypes = [
      'image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'image/tiff',
      'application/pdf', 'application/zip', 'application/gzip', 'application/x-rar',
      'application/vnd.ms-office', 'video/', 'audio/', 'application/x-msdownload',
      'application/x-elf', 'application/java-vm', 'application/x-mach-binary'
    ]

    const isBinary = knownBinaryTypes.some(type => realType.mimeType.startsWith(type))

    if (isBinary) {
      return {
        valid: false,
        warning: `SECURITY WARNING: "${file.name}" claims to be a text file (.${declaredExt}) but appears to be a binary file (${realType.mimeType})`,
        shouldBlock: true,
        detectedType: realType
      }
    }
  }

  // Warn about SIGNIFICANT type mismatches (not generic binaries)
  if (expectedTypes[declaredExt]) {
    if (!expectedTypes[declaredExt].includes(realType.mimeType)) {
      // Ignore warnings for unknown/generic binaries
      if (realType.mimeType !== 'application/octet-stream' && realType.category !== 'unknown') {
        return {
          valid: true,
          warning: `Type mismatch: "${file.name}" claims to be .${declaredExt} but appears to be ${realType.mimeType}`,
          shouldBlock: false,
          detectedType: realType
        }
      }
    }
  }

  return { valid: true, detectedType: realType }
}

/**
 * Validate file size is within limits
 */
export const validateFileSize = (file: File, maxSizeMB: number = 10): FileValidationResult => {
  const maxSizeBytes = maxSizeMB * 1024 * 1024

  if (file.size > maxSizeBytes) {
    return {
      valid: false,
      warning: `File "${file.name}" is too large (${(file.size / 1024 / 1024).toFixed(2)}MB). Maximum size is ${maxSizeMB}MB.`,
      shouldBlock: true
    }
  }

  return { valid: true }
}

/**
 * Comprehensive file validation combining size and type checks
 */
export const validateFile = async (file: File, maxSizeMB: number = 10): Promise<FileValidationResult> => {
  // Check size first (faster)
  const sizeValidation = validateFileSize(file, maxSizeMB)
  if (!sizeValidation.valid) {
    return sizeValidation
  }

  // Check file type and security
  const typeValidation = await validateFileType(file)
  return typeValidation
}

/**
 * Validate multiple files at once
 */
export const validateFiles = async (
  files: File[],
  maxSizeMB: number = 10
): Promise<{
  validFiles: File[]
  invalidFiles: Array<{ file: File; reason: string }>
  blockedFiles: Array<{ file: File; reason: string }>
  warnings: Array<{ file: File; message: string }>
}> => {
  const validFiles: File[] = []
  const invalidFiles: Array<{ file: File; reason: string }> = []
  const blockedFiles: Array<{ file: File; reason: string }> = []
  const warnings: Array<{ file: File; message: string }> = []

  for (const file of files) {
    const validation = await validateFile(file, maxSizeMB)

    if (validation.shouldBlock) {
      blockedFiles.push({
        file,
        reason: validation.warning || 'File blocked for security reasons'
      })
    } else if (!validation.valid) {
      invalidFiles.push({
        file,
        reason: validation.warning || 'Invalid file'
      })
    } else {
      validFiles.push(file)

      if (validation.warning) {
        warnings.push({
          file,
          message: validation.warning
        })
      }
    }
  }

  return { validFiles, invalidFiles, blockedFiles, warnings }
}
