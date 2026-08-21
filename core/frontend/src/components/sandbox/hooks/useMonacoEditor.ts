/**
 * Custom hook for Monaco Editor operations
 */

import { useRef, useEffect, useCallback } from 'react'
import type { Monaco, OnMount } from '@monaco-editor/react'

// Editor/model types derived from @monaco-editor/react so they always match
// the monaco-editor copy that library resolves (monaco-editor itself is not a
// direct dependency of this project — only a peer of @monaco-editor/react).
type IStandaloneCodeEditor = Parameters<OnMount>[0]
type ITextModel = NonNullable<ReturnType<IStandaloneCodeEditor['getModel']>>

export function useMonacoEditor() {
  const editorRef = useRef<IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)
  const modelsRef = useRef<Map<string, ITextModel>>(new Map())
  const activeFilePathRef = useRef<string | null>(null)
  const isChangingFileRef = useRef(false)
  const isSavingRef = useRef(false)

  // Switch to model for active file
  const switchToFileModel = useCallback((filePath: string, fileContent: string, language: string) => {
    if (!editorRef.current || !monacoRef.current) return

    isChangingFileRef.current = true

    try {
      let model = modelsRef.current.get(filePath)

      // Check if model exists but is disposed (can happen after closing and reopening)
      if (model && model.isDisposed()) {
        modelsRef.current.delete(filePath)
        model = undefined
      }

      if (!model) {
        const uri = monacoRef.current.Uri.file(filePath)

        // Check if Monaco has an existing model for this URI (might be disposed)
        const existingModel = monacoRef.current.editor.getModel(uri)
        if (existingModel) {
          if (existingModel.isDisposed()) {
            // Model is disposed but still in Monaco's registry - we need to create fresh
            // Monaco should clean this up, but let's be safe
          } else {
            // Model exists and is not disposed - reuse it but update content
            existingModel.setValue(fileContent)
            model = existingModel
          }
        }

        if (!model) {
          model = monacoRef.current.editor.createModel(fileContent, language, uri)
        }
        if (!model) {
          // Caught below alongside disposed-editor errors
          throw new Error(`Failed to create Monaco model for ${filePath}`)
        }
        modelsRef.current.set(filePath, model)
      }

      editorRef.current.setModel(model)
      activeFilePathRef.current = filePath
    } catch (error) {
      // Editor may have been disposed - silently ignore
      console.debug('[Monaco] Editor disposed, ignoring model switch:', error)
    }

    setTimeout(() => {
      isChangingFileRef.current = false
    }, 100)
  }, [])

  // Dispose model for file
  const disposeModel = useCallback((filePath: string) => {
    const model = modelsRef.current.get(filePath)
    if (model) {
      // If this model is currently active in the editor, clear it first
      // to avoid "Model is disposed" errors during theme changes
      if (editorRef.current && editorRef.current.getModel() === model) {
        editorRef.current.setModel(null)
      }
      model.dispose()
      modelsRef.current.delete(filePath)
    }
  }, [])

  // Update model after rename
  const renameModel = useCallback((oldPath: string, newPath: string, newLanguage: string) => {
    const oldModel = modelsRef.current.get(oldPath)
    if (oldModel && monacoRef.current) {
      try {
        const newUri = monacoRef.current.Uri.file(newPath)
        const newModel = monacoRef.current.editor.createModel(
          oldModel.getValue(),
          newLanguage,
          newUri
        )

        oldModel.dispose()
        modelsRef.current.delete(oldPath)
        modelsRef.current.set(newPath, newModel)

        if (activeFilePathRef.current === oldPath && editorRef.current) {
          editorRef.current.setModel(newModel)
          activeFilePathRef.current = newPath
        }

        return newModel
      } catch (error) {
        // Editor may have been disposed - silently ignore
        console.debug('[Monaco] Editor disposed, ignoring model rename')
        return null
      }
    }
    return null
  }, [])

  // Get current content from editor
  const getCurrentContent = useCallback((): string | null => {
    if (!editorRef.current) return null
    try {
      const model = editorRef.current.getModel()
      return model ? model.getValue() : null
    } catch (error) {
      // Editor may have been disposed - silently ignore
      console.debug('[Monaco] Editor disposed, ignoring content retrieval')
      return null
    }
  }, [])

  // Force layout recalculation (useful after container resize)
  const forceLayout = useCallback(() => {
    if (!editorRef.current) return
    try {
      editorRef.current.layout()
    } catch (error) {
      console.debug('[Monaco] Editor disposed, ignoring layout request')
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      modelsRef.current.forEach(model => model.dispose())
      modelsRef.current.clear()
    }
  }, [])

  return {
    editorRef,
    monacoRef,
    modelsRef,
    activeFilePathRef,
    isChangingFileRef,
    isSavingRef,
    switchToFileModel,
    disposeModel,
    renameModel,
    getCurrentContent,
    forceLayout,
  }
}
