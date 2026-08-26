/**
 * Custom hook for Monaco editor lifecycle: theme application, the
 * onMount wiring (content-change tracking, the editor's own Ctrl/Cmd+S
 * command, cursor/selection tracking), and switching the active model
 * once Monaco is ready.
 */

import { useEffect, useRef, useState } from 'react'
import type { OnMount } from '@monaco-editor/react'
import { fsAPI } from '@/api/fs'
import { toErrorMessage } from '@/utils/errorMessages'
import { getMonacoThemeData, type CodeThemeId } from '@/constants/codeThemes'
import type { OpenFile } from '../types'
import type { useMonacoEditor } from './useMonacoEditor'

interface ToastFn {
  (options: { title: string; description?: string; variant?: 'default' | 'destructive' }): void
}

interface UseEditorMountParams {
  editorHook: ReturnType<typeof useMonacoEditor>
  codeThemeId: CodeThemeId
  toast: ToastFn
  userId?: string
  projectId: string
  activeFilePath: string | null
  activeFile: OpenFile | undefined
  openFilesRef: React.MutableRefObject<OpenFile[]>
  setOpenFiles: React.Dispatch<React.SetStateAction<OpenFile[]>>
}

export function useEditorMount({
  editorHook,
  codeThemeId,
  toast,
  userId,
  projectId,
  activeFilePath,
  activeFile,
  openFilesRef,
  setOpenFiles,
}: UseEditorMountParams) {
  const [monacoReady, setMonacoReady] = useState(false)
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 })
  const [selectedTextLength, setSelectedTextLength] = useState(0)
  const themeDefinedRef = useRef<Set<string>>(new Set())
  const userIdRef = useRef<string | undefined>(userId)
  const projectIdRef = useRef<string>(projectId)

  useEffect(() => {
    userIdRef.current = userId
  }, [userId])

  useEffect(() => {
    projectIdRef.current = projectId
  }, [projectId])

  // Apply code theme from settings when it changes
  useEffect(() => {
    const monaco = editorHook.monacoRef.current
    if (!monaco) return
    const themeName = `custom-${codeThemeId}`
    if (!themeDefinedRef.current.has(themeName)) {
      themeDefinedRef.current.add(themeName)
      monaco.editor.defineTheme(themeName, getMonacoThemeData(codeThemeId))
    }
    monaco.editor.setTheme(themeName)
  }, [codeThemeId])

  // Switch Monaco model when active file changes
  useEffect(() => {
    if (monacoReady && activeFilePath && activeFile) {
      editorHook.switchToFileModel(activeFilePath, activeFile.content, activeFile.language)
    }
  }, [monacoReady, activeFilePath, activeFile, editorHook.switchToFileModel])

  // Monaco editor setup
  const handleEditorDidMount: OnMount = (editor, monacoInstance) => {
    editorHook.editorRef.current = editor
    editorHook.monacoRef.current = monacoInstance

    // Disable semantic validation — Monaco has no access to the sandbox's
    // node_modules or tsconfig, so every import would show as an error.
    const diagOpts = { noSemanticValidation: true, noSyntaxValidation: false }
    monacoInstance.languages.typescript.typescriptDefaults.setDiagnosticsOptions(diagOpts)
    monacoInstance.languages.typescript.javascriptDefaults.setDiagnosticsOptions(diagOpts)

    // Define and apply the selected code theme from settings
    const themeName = `custom-${codeThemeId}`
    if (!themeDefinedRef.current.has(themeName)) {
      themeDefinedRef.current.add(themeName)
      monacoInstance.editor.defineTheme(themeName, getMonacoThemeData(codeThemeId))
    }
    monacoInstance.editor.setTheme(themeName)

    editor.onDidChangeModelContent(() => {
      if (editorHook.isChangingFileRef.current || editorHook.isSavingRef.current) {
        return
      }

      const currentPath = editorHook.activeFilePathRef.current
      const currentModel = editor.getModel()

      if (currentPath && currentModel) {
        const currentContent = currentModel.getValue()

        setOpenFiles(prevFiles => prevFiles.map(f =>
          f.path === currentPath
            ? { ...f, content: currentContent, isDirty: true }
            : f
        ))
      }
    })

    editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, () => {
      const currentActiveFilePath = editorHook.activeFilePathRef.current
      const currentUserId = userIdRef.current

      if (currentActiveFilePath && currentUserId) {
        const currentModel = editor.getModel()
        if (!currentModel) return

        const currentContent = currentModel.getValue()
        const file = openFilesRef.current.find(f => f.path === currentActiveFilePath)
        if (!file) return

        editorHook.isSavingRef.current = true

        fsAPI.writeFile({
          user_id: currentUserId,
          conversation_id: projectIdRef.current,
          chat_id: projectIdRef.current,
          sync_mode: true,
          path: currentActiveFilePath,
          content: currentContent,
        }).then(result => {
          if (result.success) {
            setOpenFiles(prevFiles => prevFiles.map(f =>
              f.path === currentActiveFilePath ? { ...f, content: currentContent, isDirty: false } : f
            ))
          } else {
            toast({
              title: 'Failed to save file',
              description: result.error || 'Unknown error',
              variant: 'destructive',
            })
          }
        }).catch(error => {
          toast({
            title: 'Error',
            description: toErrorMessage(error) || 'Failed to save file',
            variant: 'destructive',
          })
        }).finally(() => {
          setTimeout(() => {
            editorHook.isSavingRef.current = false
          }, 100)
        })
      }
    })

    // Track cursor position for status bar
    editor.onDidChangeCursorPosition((e) => {
      setCursorPosition({ line: e.position.lineNumber, column: e.position.column })
    })

    // Track selection for status bar
    editor.onDidChangeCursorSelection((e) => {
      const selection = e.selection
      if (selection.isEmpty()) {
        setSelectedTextLength(0)
      } else {
        const model = editor.getModel()
        if (model) {
          const selectedText = model.getValueInRange(selection)
          setSelectedTextLength(selectedText.length)
        }
      }
    })

    // Set Monaco ready state to trigger file loading
    setMonacoReady(true)
  }

  return {
    monacoReady,
    cursorPosition,
    selectedTextLength,
    handleEditorDidMount,
  }
}
