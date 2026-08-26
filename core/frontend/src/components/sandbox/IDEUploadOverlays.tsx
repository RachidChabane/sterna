/**
 * Drag & drop overlay, upload-progress overlay, and the hidden file
 * input used by the "Import" button — the full-screen UI feedback for
 * FullIDE's upload flow.
 */

import { Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { MAX_FILE_SIZE_LABEL } from './fileUploadUtils'

interface UploadProgress {
  current: number
  total: number
  currentFileName: string
}

interface IDEUploadOverlaysProps {
  isDraggingFiles: boolean
  isUploading: boolean
  uploadProgress: UploadProgress | null
  fileInputRef: React.RefObject<HTMLInputElement | null>
  onCancelUpload: () => void
  onFileInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}

export function IDEUploadOverlays({
  isDraggingFiles,
  isUploading,
  uploadProgress,
  fileInputRef,
  onCancelUpload,
  onFileInputChange,
}: IDEUploadOverlaysProps) {
  return (
    <>
      {/* Drag & Drop Overlay */}
      {isDraggingFiles && (
        <div className="absolute inset-0 z-50 bg-slate-950/90 backdrop-blur-sm flex items-center justify-center pointer-events-none">
          <div className="text-center space-y-4">
            <div className="mx-auto w-20 h-20 rounded-full bg-accent-brand/20 flex items-center justify-center">
              <Upload className="w-10 h-10 text-accent-brand" />
            </div>
            <div className="space-y-2">
              <p className="text-xl font-semibold text-white">Drop files to upload</p>
              <p className="text-sm text-slate-400">Files will be uploaded to /workspace</p>
              <p className="text-xs text-slate-500">Maximum file size: {MAX_FILE_SIZE_LABEL}</p>
            </div>
          </div>
        </div>
      )}

      {/* Upload Progress Overlay */}
      {isUploading && (
        <div className="absolute inset-0 z-50 bg-slate-950/90 backdrop-blur-sm flex items-center justify-center">
          <div className="text-center space-y-4 max-w-md w-full px-6">
            <div className="mx-auto w-16 h-16 rounded-full bg-accent-brand/20 flex items-center justify-center">
              <Upload className="w-8 h-8 text-accent-brand animate-bounce" />
            </div>

            <div className="space-y-3">
              <p className="text-lg font-semibold text-white">Uploading files...</p>

              {uploadProgress && (
                <>
                  {/* Progress bar */}
                  <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-accent-brand h-full transition-all duration-300 ease-out"
                      style={{
                        width: `${uploadProgress.total > 0 ? ((uploadProgress.current + 1) / uploadProgress.total) * 100 : 0}%`
                      }}
                    />
                  </div>

                  {/* Progress text */}
                  <div className="space-y-1">
                    <p className="text-sm text-slate-300">
                      {uploadProgress.current + 1} of {uploadProgress.total} files
                    </p>
                    <p className="text-xs text-slate-500 truncate max-w-full" title={uploadProgress.currentFileName}>
                      {uploadProgress.currentFileName}
                    </p>
                  </div>
                </>
              )}

              {/* Cancel button */}
              <Button
                variant="outline"
                size="sm"
                onClick={onCancelUpload}
                className="mt-2 border-red-500/50 text-red-400 hover:bg-red-500/10 hover:border-red-500"
              >
                <X className="w-4 h-4 mr-1.5" />
                Cancel Upload
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Hidden file input for Import button */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={onFileInputChange}
        className="hidden"
        accept="*/*"
      />
    </>
  )
}
