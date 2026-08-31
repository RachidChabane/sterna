import { useState, useMemo } from 'react'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { ChevronRight, ChevronLeft, X } from 'lucide-react'
import { StepIndicator } from './createRoomModal/StepIndicator'
import { MobileBasicsStep } from './createRoomModal/MobileBasicsStep'
import { DesktopBasicsStep } from './createRoomModal/DesktopBasicsStep'
import { MobileAgentsStep } from './createRoomModal/MobileAgentsStep'
import { DesktopAgentsStep } from './createRoomModal/DesktopAgentsStep'
import { MobileVoiceStep } from './createRoomModal/MobileVoiceStep'
import { DesktopVoiceStep } from './createRoomModal/DesktopVoiceStep'
import { MODAL_STEPS } from './createRoomModal/steps'
import { useAgentRoster } from './createRoomModal/useAgentRoster'
import { useTtsProviderModels } from './createRoomModal/useTtsProviderModels'
import { useRoomFormPopulation } from './createRoomModal/useRoomFormPopulation'
import { useRoomSubmission } from './createRoomModal/useRoomSubmission'
import { DEFAULT_VOICE_SETTINGS } from './createRoomModal/constants'
import type { RoomPreset, VoiceSettingsFormState } from './createRoomModal/types'
import { useAuthStore } from '@/store/authStore'
import type { VoiceRoom, VoiceSettings } from '@/types/voiceRoom'

export type { RoomPreset } from './createRoomModal/types'

interface CreateRoomModalProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (room: VoiceRoom) => void
  roomToEdit?: VoiceRoom | null // If provided, modal is in edit mode
  preset?: RoomPreset | null // If provided, pre-fills the form
}

export function CreateRoomModal({ isOpen, onClose, onCreated, roomToEdit, preset }: CreateRoomModalProps) {
  const { user } = useAuthStore()
  const isMobile = useMediaQuery('(max-width: 640px)')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [userName, setUserName] = useState('')
  const [language, setLanguage] = useState('auto')
  const [voiceSettings, setVoiceSettings] = useState<VoiceSettingsFormState>({ ...DEFAULT_VOICE_SETTINGS })
  const [aiGenerateOpen, setAiGenerateOpen] = useState(false)
  const [aiDescription, setAiDescription] = useState('')
  const [mobileStep, setMobileStep] = useState(1)

  const isEditMode = !!roomToEdit

  const {
    agents, setAgents, expandedAgents,
    handleAddAgent, handleRemoveAgent, handleAgentChange, handleToggleAgentExpand,
    sensors, handleDragEnd,
  } = useAgentRoster()

  const {
    selectedProvider, setSelectedProvider, resetVoiceValidation,
    ttsProviders, ttsModels, recommendedVoices, voiceRoomModels,
  } = useTtsProviderModels(isOpen, setAgents, voiceSettings, setVoiceSettings)

  // Get available languages for the selected TTS model
  const availableLanguages = useMemo(() => {
    const selectedModel = ttsModels.find(m => m.model_id === voiceSettings.tts_model)
    return selectedModel?.languages || []
  }, [ttsModels, voiceSettings.tts_model])

  // Get default user name from auth store (first name only)
  const defaultUserName = user?.first_name || ''

  useRoomFormPopulation(
    isOpen, roomToEdit, preset, defaultUserName, recommendedVoices, agents, resetVoiceValidation,
    { setName, setDescription, setUserName, setLanguage, setVoiceSettings, setSelectedProvider, setAgents, setMobileStep },
  )

  const { isCreating, isGeneratingRoom, handleAIGenerate, handleSubmit, isFormValid, canProceedFromStep } = useRoomSubmission(
    { name, description, userName, language, agents, voiceSettings, selectedProvider, isEditMode, roomToEdit, defaultUserName, aiDescription },
    { setName, setDescription, setUserName, setLanguage, setVoiceSettings, setAgents, setAiGenerateOpen, setAiDescription },
    onCreated,
  )

  const handleVoiceSettingChange = (key: keyof VoiceSettings, value: number | boolean | string) => {
    setVoiceSettings(prev => ({ ...prev, [key]: value }))
  }

  const basicsStepProps = {
    isEditMode,
    aiDescription,
    setAiDescription,
    isGeneratingRoom,
    handleAIGenerate,
    name,
    setName,
    userName,
    setUserName,
    description,
    setDescription,
    language,
    setLanguage,
    availableLanguages,
  }

  const agentsStepProps = {
    agents,
    handleAddAgent,
    handleRemoveAgent,
    handleAgentChange,
    voiceRoomModels,
    recommendedVoices,
    selectedProvider,
    voiceSettings,
  }

  const voiceStepProps = {
    ttsProviders,
    ttsModels,
    selectedProvider,
    setSelectedProvider,
    voiceSettings,
    setVoiceSettings,
    handleVoiceSettingChange,
  }

  const renderMobileStepContent = () => {
    switch (mobileStep) {
      case 1:
        return <MobileBasicsStep {...basicsStepProps} />
      case 2:
        return <MobileAgentsStep {...agentsStepProps} />
      case 3:
        return <MobileVoiceStep {...voiceStepProps} />
      default:
        return null
    }
  }

  const renderDesktopStepContent = () => {
    switch (mobileStep) {
      case 1:
        return <DesktopBasicsStep {...basicsStepProps} />
      case 2:
        return (
          <DesktopAgentsStep
            {...agentsStepProps}
            expandedAgents={expandedAgents}
            handleToggleAgentExpand={handleToggleAgentExpand}
            sensors={sensors}
            handleDragEnd={handleDragEnd}
            language={language}
          />
        )
      case 3:
        return <DesktopVoiceStep {...voiceStepProps} />
      default:
        return null
    }
  }

  // Mobile UI - Full screen sheet with steps
  if (isMobile) {
    return (
      <Sheet open={isOpen} onOpenChange={onClose}>
        <SheetContent side="bottom" className="h-[85vh] rounded-t-2xl p-0 flex flex-col [&>button]:hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b shrink-0">
            <div className="flex items-center gap-3">
              {mobileStep > 1 && (
                <button
                  onClick={() => setMobileStep(mobileStep - 1)}
                  className="p-1 -ml-1 rounded-md text-muted-foreground hover:text-foreground"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
              )}
              <SheetTitle className="text-base">
                {isEditMode ? 'Edit Room' : 'Create Room'}
              </SheetTitle>
            </div>
            <button
              onClick={onClose}
              className="p-1 -mr-1 rounded-md text-muted-foreground hover:text-foreground"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Step indicator */}
          <StepIndicator steps={MODAL_STEPS} currentStep={mobileStep} onSelectStep={setMobileStep} variant="mobile" />

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-4 py-4">
            <div
              key={mobileStep}
              className="animate-in fade-in-0 slide-in-from-right-4 duration-200"
            >
              {renderMobileStepContent()}
            </div>
          </div>

          {/* Footer */}
          <div className="shrink-0 border-t p-4 bg-background">
            {mobileStep < 3 ? (
              <Button
                onClick={() => setMobileStep(mobileStep + 1)}
                disabled={!canProceedFromStep(mobileStep)}
                className="w-full h-11"
              >
                Continue
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={isCreating || !isFormValid}
                className="w-full h-11"
              >
                {isCreating
                  ? isEditMode ? 'Saving...' : 'Creating...'
                  : isEditMode ? 'Save Changes' : 'Create Room'}
              </Button>
            )}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  // Desktop UI - Step-based dialog
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl h-[85vh] max-h-[700px] p-0 gap-0 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b shrink-0">
          <DialogTitle className="text-lg font-semibold">
            {isEditMode ? 'Edit Voice Room' : 'Create Voice Room'}
          </DialogTitle>
        </div>

        {/* Step indicator */}
        <StepIndicator steps={MODAL_STEPS} currentStep={mobileStep} onSelectStep={setMobileStep} variant="desktop" />

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5 min-h-0">
          <div
            key={mobileStep}
            className="h-full animate-in fade-in-0 slide-in-from-right-4 duration-200"
          >
            {renderDesktopStepContent()}
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t px-6 py-4 flex items-center justify-between bg-background">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <div className="flex items-center gap-2">
            {mobileStep > 1 && (
              <Button
                variant="outline"
                onClick={() => setMobileStep(mobileStep - 1)}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Back
              </Button>
            )}
            {mobileStep < 3 ? (
              <Button
                onClick={() => setMobileStep(mobileStep + 1)}
                disabled={!canProceedFromStep(mobileStep)}
              >
                Continue
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                disabled={isCreating || !isFormValid}
              >
                {isCreating
                  ? isEditMode ? 'Saving...' : 'Creating...'
                  : isEditMode ? 'Save Changes' : 'Create Room'}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
