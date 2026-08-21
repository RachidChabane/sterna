/**
 * ChatModals Component
 *
 * Manages non-attachment modals:
 * - Model Details Modal
 * - Clear Chat Confirmation
 */

import { ModelDetailsModal } from './ModelDetailsModal'
import { ConfirmDeleteModal } from '@/components/shared'
import type { Model } from './types'
import type { ModelCatalogEntry } from '@/types/models'

interface ChatModalsProps {
  // Model Details Modal
  isModelDetailsOpen: boolean
  setIsModelDetailsOpen: (open: boolean) => void
  selectedModelDetails: ModelCatalogEntry | null
  model: Model | null
  models: Model[]
  onModelSelect: (model: Model) => void

  // Clear Chat Dialog
  showClearDialog: boolean
  setShowClearDialog: (show: boolean) => void
  onClearChat?: (deleteWorkspace?: boolean) => void
}

export function ChatModals({
  isModelDetailsOpen,
  setIsModelDetailsOpen,
  selectedModelDetails,
  model,
  models,
  onModelSelect,
  showClearDialog,
  setShowClearDialog,
  onClearChat,
}: ChatModalsProps) {
  return (
    <>
      {/* Clear Chat Confirmation Dialog */}
      <ConfirmDeleteModal
        isOpen={showClearDialog}
        onClose={() => setShowClearDialog(false)}
        onConfirm={(deleteWorkspace) => onClearChat?.(deleteWorkspace)}
        title="Clear Chat?"
        description="This will permanently delete all messages in this chat. Your analysis and recommendations will remain intact."
        showWorkspaceCheckbox={true}
        workspaceCheckboxLabel="Also delete workspace files"
      />

      {/* Model Details Modal (same as /models) */}
      <ModelDetailsModal
        isOpen={isModelDetailsOpen}
        onClose={() => setIsModelDetailsOpen(false)}
        model={selectedModelDetails}
        onSelectModel={(entry) => {
          // When selecting a model from details, apply to this chat if possible
          const selected = models.find(m => m.model_id === entry.model_id)
          if (selected) {
            onModelSelect(selected)
          }
        }}
        selectedModelId={model?.model_id}
      />
    </>
  )
}
