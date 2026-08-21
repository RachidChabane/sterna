import { useState, useEffect } from 'react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { Star } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { SortableFavoriteItem } from './SortableFavoriteItem'
import { ModelDetailsModal } from './ModelDetailsModal'
import { ConfirmDeleteModal } from '@/components/shared'
import useModelStore from '@/store/modelStore'
import { useToast } from '@/hooks/use-toast'
import type { ModelCatalogEntry } from '@/types/models'

interface FavoriteModelsModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FavoriteModelsModal({ open, onOpenChange }: FavoriteModelsModalProps) {
  const { models, favorites, removeFavorite, reorderFavorites, currentModel } = useModelStore()
  const { toast } = useToast()
  const [orderedFavoriteIds, setOrderedFavoriteIds] = useState<string[]>([])
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const [selectedModel, setSelectedModel] = useState<ModelCatalogEntry | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [modelToRemove, setModelToRemove] = useState<ModelCatalogEntry | null>(null)

  // Setup drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // 8px de mouvement avant que le drag commence
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Initialize ordered IDs from favorites
  useEffect(() => {
    if (open) {
      setOrderedFavoriteIds(favorites.map(f => f.model_id))
    }
  }, [open, favorites])

  // Get favorite models with full details in the current order
  const getFavoriteModelsInOrder = () => {
    return orderedFavoriteIds
      .map(id => {
        const fav = favorites.find(f => f.model_id === id)
        return fav?.details || models.find(m => m.model_id === id)
      })
      .filter(m => m !== undefined)
  }

  const favoriteModels = getFavoriteModelsInOrder()

  // Handle drag end
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      setOrderedFavoriteIds((items) => {
        const oldIndex = items.indexOf(active.id as string)
        const newIndex = items.indexOf(over.id as string)
        const newOrder = arrayMove(items, oldIndex, newIndex)

        // Update the store with the new order
        reorderFavorites(newOrder)

        return newOrder
      })
    }
  }

  const handleRemoveClick = (modelId: string) => {
    const model = favoriteModels.find(m => m.model_id === modelId)
    if (model) {
      setModelToRemove(model)
      setDeleteDialogOpen(true)
    }
  }

  const handleRemoveConfirm = () => {
    if (modelToRemove) {
      removeFavorite(modelToRemove.model_id)
      setOrderedFavoriteIds(prev => prev.filter(id => id !== modelToRemove.model_id))

      toast({
        title: "Removed from favorites",
        description: `${modelToRemove.name} has been removed from your favorites.`,
      })

      setModelToRemove(null)
    }
  }

  const handleModelClick = (model: ModelCatalogEntry) => {
    setSelectedModel(model)
    setDetailsModalOpen(true)
  }

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
            Manage Favorite Models
          </DialogTitle>
          <DialogDescription>
            Drag and drop to reorder your favorite models. The order will be reflected throughout the app.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto pr-2 -mr-2">
          {favoriteModels.length === 0 ? (
            <Alert>
              <AlertDescription>
                You don't have any favorite models yet. Add models to favorites from the model catalog.
              </AlertDescription>
            </Alert>
          ) : (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={orderedFavoriteIds}
                strategy={verticalListSortingStrategy}
              >
                <div className="space-y-2">
                  {favoriteModels.map((model) => (
                    <SortableFavoriteItem
                      key={model.model_id}
                      model={model}
                      onRemove={handleRemoveClick}
                      onModelClick={handleModelClick}
                      isCurrentModel={currentModel?.model_id === model.model_id}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          )}
        </div>
      </DialogContent>

      {/* Model Details Modal */}
      <ModelDetailsModal
        model={selectedModel}
        isOpen={detailsModalOpen}
        onClose={() => setDetailsModalOpen(false)}
      />
    </Dialog>

    {/* Remove Confirmation Dialog */}
    {modelToRemove && (
      <ConfirmDeleteModal
        isOpen={deleteDialogOpen}
        onClose={() => {
          setDeleteDialogOpen(false)
          setModelToRemove(null)
        }}
        onConfirm={handleRemoveConfirm}
        title="Remove from Favorites"
        description={`Are you sure you want to remove ${modelToRemove.name} from your favorites?`}
      />
    )}
    </>
  )
}
