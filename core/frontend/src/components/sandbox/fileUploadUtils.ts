/**
 * Pure helpers for file upload validation and reading.
 *
 * Shared by the upload/drag-drop flow (useFileUpload) and the file-download
 * flow (useFileOperations), which both need to detect a file's real type
 * from its magic bytes before trusting its declared extension.
 */

// File upload size limit (300MB)
export const MAX_FILE_SIZE_BYTES = 300 * 1024 * 1024
export const MAX_FILE_SIZE_LABEL = '300MB'

// Detect real file type using magic bytes (file signature)
export const detectRealFileType = async (file: File): Promise<{ mime: string; category: string }> => {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const arr = new Uint8Array(e.target?.result as ArrayBuffer).subarray(0, 16)
      let header = ''
      for (let i = 0; i < arr.length && i < 8; i++) {
        header += arr[i].toString(16).padStart(2, '0')
      }

      // Magic bytes signatures (most common)
      const signatures: Record<string, { mime: string; category: string }> = {
        // Images
        '89504e47': { mime: 'image/png', category: 'image' },
        'ffd8ffe0': { mime: 'image/jpeg', category: 'image' },
        'ffd8ffe1': { mime: 'image/jpeg', category: 'image' },
        'ffd8ffe2': { mime: 'image/jpeg', category: 'image' },
        '47494638': { mime: 'image/gif', category: 'image' },
        '424d': { mime: 'image/bmp', category: 'image' },
        '00000100': { mime: 'image/x-icon', category: 'image' },

        // Documents
        '25504446': { mime: 'application/pdf', category: 'document' },
        '504b0304': { mime: 'application/zip', category: 'archive' }, // Also xlsx, docx
        'd0cf11e0': { mime: 'application/vnd.ms-office', category: 'document' }, // Old Office

        // Archives
        '1f8b': { mime: 'application/gzip', category: 'archive' },
        '526172': { mime: 'application/x-rar', category: 'archive' },
        '377abcaf': { mime: 'application/x-7z-compressed', category: 'archive' },
        '425a68': { mime: 'application/x-bzip2', category: 'archive' },

        // Executables
        '4d5a': { mime: 'application/x-msdownload', category: 'executable' }, // .exe, .dll
        '7f454c46': { mime: 'application/x-elf', category: 'executable' }, // Linux executable
        'cafebabe': { mime: 'application/java-vm', category: 'executable' }, // Java class
        'feedface': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS binary
        'cefaedfe': { mime: 'application/x-mach-binary', category: 'executable' }, // macOS binary

        // Media
        '000001ba': { mime: 'video/mpeg', category: 'media' },
        '000001b3': { mime: 'video/mpeg', category: 'media' },
        '66747970': { mime: 'video/mp4', category: 'media' },
        '494433': { mime: 'audio/mpeg', category: 'media' }, // MP3
        '52494646': { mime: 'audio/wav', category: 'media' }, // WAV
      }

      // Check for matches (try different header lengths)
      for (let len = 8; len >= 2; len--) {
        const truncated = header.substring(0, len * 2)
        if (signatures[truncated]) {
          return resolve(signatures[truncated])
        }
      }

      resolve({ mime: 'application/octet-stream', category: 'unknown' })
    }
    reader.readAsArrayBuffer(file.slice(0, 16))
  })
}

// Validate that a file's real type matches its declared extension
export const validateFileType = async (file: File): Promise<{ valid: boolean; warning?: string; shouldBlock?: boolean }> => {
  const declaredExt = file.name.split('.').pop()?.toLowerCase() || ''
  const realType = await detectRealFileType(file)

  // Define text/code file extensions (should NOT be binary)
  const textExtensions = ['txt', 'md', 'py', 'js', 'ts', 'tsx', 'jsx', 'java', 'cpp', 'c', 'h', 'css', 'scss', 'html', 'xml', 'json', 'yaml', 'yml', 'sh', 'bash', 'sql', 'rs', 'go', 'php', 'rb', 'swift', 'kt', 'cs', 'r', 'scala', 'dart']

  // Define expected MIME types for common extensions
  const expectedTypes: Record<string, string[]> = {
    'png': ['image/png'],
    'jpg': ['image/jpeg'],
    'jpeg': ['image/jpeg'],
    'gif': ['image/gif'],
    'bmp': ['image/bmp'],
    'ico': ['image/x-icon'],
    'pdf': ['application/pdf'],
    'zip': ['application/zip', 'application/octet-stream'], // ZIP or generic binary
    'gz': ['application/gzip', 'application/octet-stream'],
    'rar': ['application/x-rar', 'application/octet-stream'],
    '7z': ['application/x-7z-compressed', 'application/octet-stream'],
    'tar': ['application/x-tar', 'application/octet-stream'],
    'mp3': ['audio/mpeg', 'application/octet-stream'],
    'wav': ['audio/wav', 'application/octet-stream'],
    'mp4': ['video/mp4', 'application/octet-stream'],
    'xlsx': ['application/zip', 'application/octet-stream'], // Excel files are ZIP archives
    'xls': ['application/vnd.ms-office', 'application/octet-stream'],
  }

  // CRITICAL: Block executables masquerading as non-executable types
  if (realType.category === 'executable' && !['exe', 'dll', 'so', 'dylib', 'elf'].includes(declaredExt)) {
    return {
      valid: false,
      warning: `SECURITY WARNING: "${file.name}" appears to be an executable file (.${declaredExt} → ${realType.mime})`,
      shouldBlock: true
    }
  }

  // CRITICAL: Block binary files (images, PDFs, etc.) masquerading as text/code files
  if (textExtensions.includes(declaredExt)) {
    // Check if the real type is a known binary format
    const knownBinaryTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/bmp', 'application/pdf',
                              'application/zip', 'application/gzip', 'application/x-rar',
                              'application/vnd.ms-office', 'video/', 'audio/']

    const isBinary = knownBinaryTypes.some(type => realType.mime.startsWith(type))

    if (isBinary) {
      return {
        valid: false,
        warning: `SECURITY WARNING: "${file.name}" claims to be a text file (.${declaredExt}) but appears to be a binary file (${realType.mime})`,
        shouldBlock: true
      }
    }
  }

  // Only warn about SIGNIFICANT type mismatches (not generic binaries)
  if (expectedTypes[declaredExt]) {
    // Check if the detected type matches expectations
    if (!expectedTypes[declaredExt].includes(realType.mime)) {
      // Ignore warnings for unknown/generic binaries (application/octet-stream)
      // Only warn if we detected a SPECIFIC different type
      if (realType.mime !== 'application/octet-stream' && realType.category !== 'unknown') {
        // Example: .png file that is actually a .pdf
        return {
          valid: true,
          warning: `Type mismatch: "${file.name}" claims to be .${declaredExt} but appears to be ${realType.mime}`,
          shouldBlock: false
        }
      }
    }
  }

  return { valid: true }
}

// Read file content with proper encoding (base64 for binary, text otherwise)
export const readFileContent = async (file: File): Promise<{ content: string; isBinary: boolean }> => {
  const isBinary = /\.(png|jpg|jpeg|gif|webp|bmp|ico|pdf|xlsx|xls|xlsm|zip|tar|gz|mp4|mp3|wav)$/i.test(file.name)

  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()

    if (isBinary) {
      reader.onload = () => {
        const base64 = (reader.result as string).split(',')[1] // Remove data:... prefix
        resolve(base64)
      }
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
      reader.readAsDataURL(file)
    } else {
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = () => reject(new Error(`Failed to read ${file.name}`))
      reader.readAsText(file)
    }
  })

  return { content, isBinary }
}

// Recursively read all files from directory entries (drag & drop)
export const readDirectoryEntries = async (entry: FileSystemEntry): Promise<Array<{ file: File; relativePath: string }>> => {
  const results: Array<{ file: File; relativePath: string }> = []

  if (entry.isFile) {
    // It's a file - read it
    const file = await new Promise<File>((resolve, reject) => {
      ;(entry as FileSystemFileEntry).file(resolve, reject)
    })
    results.push({ file, relativePath: entry.fullPath.replace(/^\//, '') })
  } else if (entry.isDirectory) {
    // It's a directory - read all entries recursively
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    const entries = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject)
    })

    for (const childEntry of entries) {
      const childResults = await readDirectoryEntries(childEntry)
      results.push(...childResults)
    }
  }

  return results
}

// Extract root path from a file path (first directory or file under /workspace)
export const getRootUploadPath = (filePath: string, relativePath: string): string => {
  // Get the first segment of the relative path (the dropped item name)
  const firstSegment = relativePath.split('/')[0]
  // Construct the full root path
  const basePath = filePath.substring(0, filePath.indexOf(relativePath))
  return `${basePath}${firstSegment}`.replace('//', '/')
}
