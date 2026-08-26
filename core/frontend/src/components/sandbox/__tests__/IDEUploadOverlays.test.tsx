import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { createRef } from 'react'
import { IDEUploadOverlays } from '../IDEUploadOverlays'

describe('IDEUploadOverlays', () => {
  it('renders the drag overlay when dragging files', () => {
    render(
      <IDEUploadOverlays
        isDraggingFiles={true}
        isUploading={false}
        uploadProgress={null}
        fileInputRef={createRef<HTMLInputElement>()}
        onCancelUpload={vi.fn()}
        onFileInputChange={vi.fn()}
      />
    )

    expect(screen.getByText('Drop files to upload')).toBeInTheDocument()
  })

  it('renders upload progress and cancels via the button', () => {
    const onCancelUpload = vi.fn()

    render(
      <IDEUploadOverlays
        isDraggingFiles={false}
        isUploading={true}
        uploadProgress={{ current: 0, total: 3, currentFileName: 'a.txt' }}
        fileInputRef={createRef<HTMLInputElement>()}
        onCancelUpload={onCancelUpload}
        onFileInputChange={vi.fn()}
      />
    )

    expect(screen.getByText('1 of 3 files')).toBeInTheDocument()
    expect(screen.getByText('a.txt')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Cancel Upload'))
    expect(onCancelUpload).toHaveBeenCalledTimes(1)
  })

  it('renders neither overlay when idle', () => {
    render(
      <IDEUploadOverlays
        isDraggingFiles={false}
        isUploading={false}
        uploadProgress={null}
        fileInputRef={createRef<HTMLInputElement>()}
        onCancelUpload={vi.fn()}
        onFileInputChange={vi.fn()}
      />
    )

    expect(screen.queryByText('Drop files to upload')).not.toBeInTheDocument()
    expect(screen.queryByText('Uploading files...')).not.toBeInTheDocument()
  })
})
