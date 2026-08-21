/**
 * Sandbox Components
 *
 * Exports sandbox-related components for IDE functionality.
 *
 * NOTE: `FullIDE` and `FileDetailsModal` are intentionally NOT re-exported
 * here. FullIDE pulls in @monaco-editor/react and the full sandbox IDE UI,
 * and is lazy-loaded from within CodeEditorModal.tsx; re-exporting it from
 * this barrel would put it back on the static import graph for every module
 * that imports `CodeEditorModal` from here, defeating the code split.
 */

export { CodeEditorModal } from './CodeEditorModal'
