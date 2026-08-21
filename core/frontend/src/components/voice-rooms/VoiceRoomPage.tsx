import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearch, useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Markdown } from '@/components/ui/markdown'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import {
  Plus,
  Mic,
  Users,
  MessageSquare,
  Zap,
  Globe,
  Volume2,
  ChevronDown,
  ChevronUp,
  Settings2,
  Hash,
  Play,
  Pause,
  UserIcon,
  Trash2,
  ArrowLeft,
  MoreHorizontal,
  Pencil,
} from 'lucide-react'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { useAuthStore } from '@/store/authStore'
import { useNavigationStore } from '@/store/navigationStore'
import { CircleFlag } from 'react-circle-flags'
import { ModelIcon } from '@/components/models/ModelIcon'
import { ModelDetailsModal } from '@/components/models/ModelDetailsModal'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import useModelStore from '@/store/modelStore'
import { RoomList } from './RoomList'
import { CreateRoomModal, type RoomPreset } from './CreateRoomModal'
import { VoiceSession } from './VoiceSession'
import type { VoiceRoom, VoiceAgent, VoiceRoomMessage } from '@/types/voiceRoom'

// Room presets for quick creation - uses fast, affordable models
const ROOM_PRESETS: Record<string, RoomPreset> = {
  debate: {
    name: 'Debate Room',
    description: 'A room where multiple AI personalities debate topics from different perspectives',
    agents: [
      {
        display_name: 'The Advocate',
        model_id: 'google/gemini-2.0-flash-lite-001',
        system_prompt: 'You are "The Advocate" - a passionate debater who argues FOR the topic being discussed. You present strong arguments, cite examples, and defend your position with conviction. Be persuasive but respectful. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#38bdf8', // sky
      },
      {
        display_name: 'The Critic',
        model_id: 'anthropic/claude-haiku-4.5',
        system_prompt: 'You are "The Critic" - a thoughtful debater who argues AGAINST the topic being discussed. You find flaws in arguments, play devil\'s advocate, and present counterpoints. Be analytical but fair. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#f472b6', // pink
      },
      {
        display_name: 'The Moderator',
        model_id: 'openai/gpt-4o-mini',
        system_prompt: 'You are "The Moderator" - a neutral facilitator who guides the debate. You summarize key points, ask probing questions, and ensure balanced discussion. You don\'t take sides but help clarify arguments. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#a78bfa', // violet
      },
    ],
  },
  brainstorm: {
    name: 'Brainstorm Session',
    description: 'Get creative ideas from different AI perspectives for your projects',
    agents: [
      {
        display_name: 'The Innovator',
        model_id: 'google/gemini-2.0-flash-lite-001',
        system_prompt: 'You are "The Innovator" - a creative thinker who generates bold, unconventional ideas. Think outside the box, propose novel solutions, and don\'t be afraid of wild ideas. Quantity over quality initially. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#fb923c', // orange
      },
      {
        display_name: 'The Analyst',
        model_id: 'anthropic/claude-haiku-4.5',
        system_prompt: 'You are "The Analyst" - a practical thinker who evaluates ideas for feasibility. You identify strengths, potential issues, and suggest improvements. Help refine raw ideas into actionable plans. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#2dd4bf', // teal
      },
      {
        display_name: 'The Connector',
        model_id: 'openai/gpt-4o-mini',
        system_prompt: 'You are "The Connector" - a synthesizer who finds patterns and combines ideas. You build on others\' suggestions, make unexpected connections, and help the team see the bigger picture. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#facc15', // yellow
      },
    ],
  },
  language: {
    name: 'Language Practice',
    description: 'Practice conversations with AI tutors for language learning',
    agents: [
      {
        display_name: 'The Tutor',
        model_id: 'google/gemini-2.0-flash-lite-001',
        system_prompt: 'You are "The Tutor" - a patient language teacher. You speak clearly, correct mistakes gently, and explain grammar when needed. Adapt to the learner\'s level. Encourage practice and celebrate progress. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#4ade80', // green
      },
      {
        display_name: 'The Conversation Partner',
        model_id: 'anthropic/claude-haiku-4.5',
        system_prompt: 'You are "The Conversation Partner" - a friendly native speaker for practice. Have natural conversations on everyday topics. Speak at a natural pace but be ready to slow down or repeat. Ask follow-up questions to keep the conversation going. Keep responses concise (2-3 sentences) for natural conversation flow.',
        color: '#818cf8', // indigo
      },
    ],
  },
}
import type { ModelCatalogEntry } from '@/types/models'
import { cn } from '@/lib/utils'

export default function VoiceRoomPage() {
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [roomToEdit, setRoomToEdit] = useState<VoiceRoom | null>(null)
  const [selectedPreset, setSelectedPreset] = useState<RoomPreset | null>(null)
  const [selectedRoom, setSelectedRoom] = useState<VoiceRoom | null>(null)
  const [isInSession, setIsInSession] = useState(false)
  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const [selectedModelForDetails, setSelectedModelForDetails] = useState<ModelCatalogEntry | null>(null)
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set())
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [roomToDelete, setRoomToDelete] = useState<VoiceRoom | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null)
  const [conversationMessages, setConversationMessages] = useState<VoiceRoomMessage[]>([])
  const [conversationLoading, setConversationLoading] = useState(false)
  const [clearConversationDialogOpen, setClearConversationDialogOpen] = useState(false)
  const [isClearingConversation, setIsClearingConversation] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const conversationEndRef = useRef<HTMLDivElement | null>(null)

  const { user } = useAuthStore()
  const { openMobileSidebar } = useNavigationStore()
  const navigate = useNavigate()
  const { new: createNew, room: roomId } = useSearch({ from: '/voice-rooms' })

  // Toggle agent expansion
  const toggleAgentExpanded = (agentId: string) => {
    setExpandedAgents(prev => {
      const next = new Set(prev)
      if (next.has(agentId)) {
        next.delete(agentId)
      } else {
        next.add(agentId)
      }
      return next
    })
  }

  const {
    rooms,
    roomsLoading,
    roomsError,
    fetchRooms,
    fetchRecommendedVoices,
    recommendedVoices,
    fetchTTSModels,
    ttsModels,
    currentRoom,
    setCurrentRoom,
    deleteRoom,
    fetchConversation,
    clearConversation,
  } = useVoiceRoomStore()

  const { allModels, fetchAllModels, allModelsLoaded } = useModelStore()

  // Helper to find model info by model_id
  const getModelInfo = (modelId: string) => {
    return allModels.find(m => m.model_id === modelId)
  }

  // Helper to get language info (name and country code) from ttsModels
  const getLanguageInfo = (languageId: string) => {
    for (const model of ttsModels) {
      const lang = model.languages.find(l => l.language_id === languageId)
      if (lang) return lang
    }
    return null
  }

  // Open model details modal
  const handleViewModelDetails = (modelId: string) => {
    const model = getModelInfo(modelId)
    if (model) {
      setSelectedModelForDetails(model as ModelCatalogEntry)
      setDetailsModalOpen(true)
    }
  }

  // Play voice preview
  const handlePlayVoicePreview = useCallback((voiceId: string) => {
    const voice = recommendedVoices.find(v => v.voice_id === voiceId)
    if (!voice?.preview_url) return

    if (playingVoiceId === voiceId) {
      // Stop current playback
      audioRef.current?.pause()
      setPlayingVoiceId(null)
      return
    }

    // Stop previous if any
    audioRef.current?.pause()

    // Play new
    const audio = new Audio(voice.preview_url)
    audioRef.current = audio
    audio.play()
    setPlayingVoiceId(voiceId)

    audio.onended = () => setPlayingVoiceId(null)
    audio.onerror = () => setPlayingVoiceId(null)
  }, [playingVoiceId, recommendedVoices])

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      audioRef.current?.pause()
    }
  }, [])

  // Fetch rooms and LLM models on mount
  // Note: TTS models and voices are fetched per-provider in CreateRoomModal
  useEffect(() => {
    fetchRooms()
    if (!allModelsLoaded) {
      fetchAllModels()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Check for selected room from command palette
  useEffect(() => {
    const selectedRoomId = sessionStorage.getItem('selected-voice-room')
    if (selectedRoomId && rooms.length > 0) {
      const room = rooms.find((r) => r.id === selectedRoomId)
      if (room) {
        setSelectedRoom(room)
      }
      sessionStorage.removeItem('selected-voice-room')
    }
  }, [rooms])

  // Handle URL search params (new room, select room)
  useEffect(() => {
    if (createNew === 'true') {
      setSelectedPreset(null)
      setIsCreateModalOpen(true)
      // Clear the search param
      navigate({ to: '/voice-rooms', search: {}, replace: true })
    }
  }, [createNew, navigate])

  // Handle room selection from URL
  useEffect(() => {
    if (roomId && rooms.length > 0) {
      const room = rooms.find((r) => r.id === roomId)
      if (room) {
        setSelectedRoom(room)
      }
      // Clear the search param
      navigate({ to: '/voice-rooms', search: {}, replace: true })
    }
  }, [roomId, rooms, navigate])

  // Fetch conversation when room is selected
  useEffect(() => {
    if (selectedRoom) {
      setConversationLoading(true)
      fetchConversation(selectedRoom.id)
        .then((messages) => {
          setConversationMessages(messages)
        })
        .finally(() => {
          setConversationLoading(false)
        })
    } else {
      setConversationMessages([])
    }
  }, [selectedRoom, fetchConversation])

  // Scroll to bottom when messages change
  useEffect(() => {
    if (conversationEndRef.current) {
      conversationEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [conversationMessages])

  // Handle clear conversation
  const handleClearConversation = async () => {
    if (!selectedRoom) return
    setIsClearingConversation(true)
    try {
      await clearConversation(selectedRoom.id)
      setConversationMessages([])
      setClearConversationDialogOpen(false)
    } finally {
      setIsClearingConversation(false)
    }
  }

  const handleStartSession = (room: VoiceRoom) => {
    setCurrentRoom(room)
    setIsInSession(true)
  }

  const handleEndSession = async () => {
    // Get the room before clearing currentRoom
    const sessionRoom = currentRoom
    setIsInSession(false)
    setCurrentRoom(null)

    // Refresh the conversation for the room that was in session
    if (sessionRoom) {
      // Ensure the session room is selected
      if (selectedRoom?.id !== sessionRoom.id) {
        setSelectedRoom(sessionRoom)
      }
      setConversationLoading(true)
      try {
        const messages = await fetchConversation(sessionRoom.id)
        setConversationMessages(messages)
      } finally {
        setConversationLoading(false)
      }
    }
  }

  const handleRoomCreated = (room: VoiceRoom) => {
    setIsCreateModalOpen(false)
    setSelectedRoom(room)
  }

  const handleEditRoom = (room: VoiceRoom) => {
    setRoomToEdit(room)
    setIsEditModalOpen(true)
  }

  const handleRoomUpdated = (room: VoiceRoom) => {
    setIsEditModalOpen(false)
    setRoomToEdit(null)
    setSelectedRoom(room)
  }

  const handleDeleteRoom = (room: VoiceRoom) => {
    setRoomToDelete(room)
    setDeleteDialogOpen(true)
  }

  const confirmDeleteRoom = async () => {
    if (!roomToDelete) return
    setIsDeleting(true)
    try {
      const success = await deleteRoom(roomToDelete.id)
      if (success && selectedRoom?.id === roomToDelete.id) {
        setSelectedRoom(null)
      }
      setDeleteDialogOpen(false)
      setRoomToDelete(null)
    } finally {
      setIsDeleting(false)
    }
  }

  // If in session, show full-screen voice session
  if (isInSession && currentRoom) {
    return (
      <VoiceSession
        room={currentRoom}
        onEnd={handleEndSession}
      />
    )
  }

  const suggestions = [
    {
      icon: MessageSquare,
      title: "Debate Room",
      description: "Create a room where multiple AI personalities debate topics",
      presetKey: 'debate' as const,
    },
    {
      icon: Zap,
      title: "Brainstorm Session",
      description: "Get creative ideas from different AI perspectives",
      presetKey: 'brainstorm' as const,
    },
    {
      icon: Globe,
      title: "Language Practice",
      description: "Practice conversations with AI tutors",
      presetKey: 'language' as const,
    },
  ]

  return (
    <div className="flex h-[calc(100vh-3.5rem)] md:h-screen bg-background overflow-hidden">
      {/* Sidebar - Desktop only */}
      <div className="hidden md:flex border-r border-border flex-col bg-card/50 w-64">
        {/* Sidebar Header */}
        <div className="px-3 py-3 border-b border-border/60 bg-card/30 flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground tracking-tight grow">Voice Rooms</span>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 rounded-lg hover:bg-secondary/80 hover:ring-1 hover:ring-border transition-all text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setSelectedPreset(null)
                    setIsCreateModalOpen(true)
                  }}
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">New voice room</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* Rooms List */}
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-1">
            {roomsLoading ? (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent-brand mb-3" />
                <p className="text-sm text-muted-foreground">Loading rooms...</p>
              </div>
            ) : roomsError ? (
              <div className="text-center py-8 px-4">
                <p className="text-sm text-destructive mb-3">{roomsError}</p>
                <Button variant="outline" size="sm" onClick={() => fetchRooms()}>
                  Retry
                </Button>
              </div>
            ) : rooms.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm py-8">
                No voice rooms yet
              </div>
            ) : (
              <RoomList
                rooms={rooms}
                selectedRoom={selectedRoom}
                onSelect={setSelectedRoom}
                onStartSession={handleStartSession}
                onEditRoom={handleEditRoom}
                onDeleteRoom={handleDeleteRoom}
                onViewModelDetails={handleViewModelDetails}
              />
            )}
          </div>
        </ScrollArea>

        {/* Sidebar Footer */}
        <div className="px-3 py-2.5 border-t border-border/60 text-[11px] text-muted-foreground text-center">
          {rooms.length} room{rooms.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {selectedRoom ? (
          /* Selected Room Details - Different layouts for mobile vs desktop */
          <div className="flex-1 flex flex-col overflow-hidden relative">
            {/* ===== MOBILE LAYOUT ===== */}
            <div className="md:hidden flex flex-col flex-1 min-h-0 overflow-hidden">
                {/* Mobile Header */}
                <div className="flex items-center gap-3 p-3 border-b bg-background">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={() => setSelectedRoom(null)}
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                  <div className="flex-1 min-w-0">
                    <h2 className="text-base font-semibold truncate">{selectedRoom.name}</h2>
                  </div>
                  <Button
                    onClick={() => handleStartSession(selectedRoom)}
                    className="btn-premium shrink-0"
                    size="sm"
                  >
                    <Mic className="h-4 w-4 mr-1.5" />
                    Start
                  </Button>
                </div>

                {/* Mobile Info Section - Compact details */}
                <div className="px-3 py-2.5 border-b bg-muted/30 space-y-2">
                  {/* Description */}
                  {selectedRoom.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2">{selectedRoom.description}</p>
                  )}

                  {/* Stats row */}
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Users className="h-3 w-3" />
                      {selectedRoom.agents?.length || 0} agents
                    </span>
                    <span>•</span>
                    {(() => {
                      const langInfo = selectedRoom.language !== 'auto' ? getLanguageInfo(selectedRoom.language) : null
                      if (langInfo?.country_code) {
                        return (
                          <span className="flex items-center gap-1">
                            <CircleFlag countryCode={langInfo.country_code.toLowerCase()} className="w-3 h-3" />
                            {langInfo.name}
                          </span>
                        )
                      }
                      return (
                        <span className="flex items-center gap-1">
                          <Globe className="h-3 w-3" />
                          {selectedRoom.language === 'auto' ? 'Auto' : selectedRoom.language?.toUpperCase()}
                        </span>
                      )
                    })()}
                  </div>

                  {/* Agent chips */}
                  <div className="flex flex-wrap gap-1.5">
                    {selectedRoom.agents?.map((agent, index) => {
                      const model = getModelInfo(agent.model_id)
                      return (
                        <button
                          key={agent.id}
                          onClick={() => handleViewModelDetails(agent.model_id)}
                          className="flex items-center gap-1.5 pl-1 pr-2 py-1 bg-background rounded-full border text-xs"
                        >
                          <ModelIcon
                            modelName={model?.name || agent.model_id || ''}
                            modelId={agent.model_id || ''}
                            provider={model?.provider || ''}
                            modelIconSlug={model?.model_icon_slug}
                            modelIconUrl={model?.model_icon_url}
                            providerIconSlug={model?.provider_icon_slug}
                            providerIconUrl={model?.provider_icon_url}
                            size={16}
                            showTooltip={false}
                          />
                          <span className="font-medium">{agent.display_name}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Mobile Conversation - Takes remaining height */}
                <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-muted/5">
                  <div className="flex items-center justify-between px-3 py-2 border-b">
                    <h3 className="text-sm font-medium">Conversation</h3>
                    {conversationMessages.length > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-muted-foreground hover:text-destructive"
                        onClick={() => setClearConversationDialogOpen(true)}
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        Clear
                      </Button>
                    )}
                  </div>
                  <ScrollArea className="flex-1">
                    <div className="p-3 space-y-3">
                      {conversationLoading ? (
                        <div className="flex flex-col items-center justify-center py-12">
                          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent-brand mb-3" />
                          <p className="text-sm text-muted-foreground">Loading...</p>
                        </div>
                      ) : conversationMessages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-center">
                          <MessageSquare className="h-10 w-10 text-muted-foreground/30 mb-3" />
                          <p className="text-sm text-muted-foreground">No conversation yet</p>
                          <p className="text-xs text-muted-foreground/70 mt-1">
                            Tap the mic button to start
                          </p>
                        </div>
                      ) : (
                        <>
                          {conversationMessages.map((message) => {
                            const isUser = message.role === 'user'
                            const agent = !isUser && message.agent_id
                              ? selectedRoom.agents?.find(a => a.id === message.agent_id)
                              : null
                            const agentModel = agent ? getModelInfo(agent.model_id) : null

                            return (
                              <div
                                key={message.id}
                                className={cn(
                                  'flex gap-2',
                                  isUser ? 'flex-row-reverse' : 'flex-row'
                                )}
                              >
                                {/* Avatar */}
                                {isUser ? (
                                  <Avatar className="h-7 w-7 shrink-0 bg-muted">
                                    {user?.avatar_url && (
                                      <AvatarImage
                                        src={user.avatar_url}
                                        alt={`${user.first_name || ''} ${user.last_name || ''}`}
                                      />
                                    )}
                                    <AvatarFallback className="bg-muted text-muted-foreground">
                                      <UserIcon className="h-3.5 w-3.5" />
                                    </AvatarFallback>
                                  </Avatar>
                                ) : (
                                  <div className="w-7 h-7 flex items-center justify-center shrink-0">
                                    {agentModel ? (
                                      <ModelIcon
                                        modelName={agentModel.name}
                                        modelId={agent?.model_id || ''}
                                        provider={agentModel.provider}
                                        modelIconSlug={agentModel.model_icon_slug}
                                        modelIconUrl={agentModel.model_icon_url}
                                        providerIconSlug={agentModel.provider_icon_slug}
                                        providerIconUrl={agentModel.provider_icon_url}
                                        size={28}
                                        showTooltip={false}
                                      />
                                    ) : (
                                      <ModelIcon
                                        modelName={message.agent_name || 'Assistant'}
                                        modelId=""
                                        provider=""
                                        size={28}
                                        showTooltip={false}
                                      />
                                    )}
                                  </div>
                                )}

                                {/* Message content */}
                                <div
                                  className={cn(
                                    'flex flex-col max-w-[80%] min-w-0',
                                    isUser ? 'items-end' : 'items-start'
                                  )}
                                >
                                  <div
                                    className={cn(
                                      'rounded-2xl px-3 py-2 text-sm',
                                      isUser
                                        ? 'bg-primary/15 text-foreground rounded-tr-sm border border-primary/20'
                                        : 'bg-card text-foreground rounded-tl-sm'
                                    )}
                                  >
                                    {isUser ? (
                                      <p className="whitespace-pre-wrap">{message.content}</p>
                                    ) : (
                                      <div className="prose prose-sm max-w-none prose-p:text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-code:text-primary">
                                        <Markdown>{message.content}</Markdown>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                          <div ref={conversationEndRef} />
                        </>
                      )}
                    </div>
                  </ScrollArea>
                </div>
              </div>

            {/* ===== DESKTOP LAYOUT ===== */}
            <div className="hidden md:flex flex-col flex-1 min-h-0 overflow-hidden p-6">
                {/* Room Header */}
                <div className="flex items-start justify-between gap-4 mb-6">
                  <div className="flex-1">
                    <h2 className="text-2xl font-semibold mb-1">{selectedRoom.name}</h2>
                    {selectedRoom.description && (
                      <p className="text-muted-foreground">{selectedRoom.description}</p>
                    )}
                  </div>
                  <Button
                    onClick={() => handleStartSession(selectedRoom)}
                    className="ml-4 btn-premium"
                    size="lg"
                  >
                    <Mic className="h-4 w-4 mr-2" />
                    Start Session
                  </Button>
                </div>

                {/* Room Stats Bar */}
                <div className="flex items-center gap-6 mb-6 pb-6 border-b">
                  <div className="flex items-center gap-2 text-sm">
                    <div className="p-1.5 rounded-md bg-accent-brand/10">
                      <Users className="h-4 w-4 text-accent-brand" />
                    </div>
                    <span className="text-muted-foreground">
                      {selectedRoom.agents?.length || 0} Agent{(selectedRoom.agents?.length || 0) !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    {(() => {
                      const langInfo = selectedRoom.language !== 'auto' ? getLanguageInfo(selectedRoom.language) : null
                      if (langInfo?.country_code) {
                        return (
                          <>
                            <span className="flex-shrink-0 w-4 h-4">
                              <CircleFlag countryCode={langInfo.country_code.toLowerCase()} className="w-full h-full" />
                            </span>
                            <span className="text-muted-foreground">{langInfo.name}</span>
                          </>
                        )
                      }
                      return (
                        <>
                          <div className="p-1.5 rounded-md bg-blue-500/10">
                            <Globe className="h-4 w-4 text-blue-500" />
                          </div>
                          <span className="text-muted-foreground">
                            {selectedRoom.language === 'auto' ? 'Auto-detect' : selectedRoom.language?.toUpperCase()}
                          </span>
                        </>
                      )
                    })()}
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    <div className="p-1.5 rounded-md bg-purple-500/10">
                      <Hash className="h-4 w-4 text-purple-500" />
                    </div>
                    <span className="text-muted-foreground">
                      {selectedRoom.max_response_tokens?.toLocaleString() || '1,024'} max tokens
                    </span>
                  </div>
                </div>

                {/* Compact Agents Strip */}
                <div className="mb-4">
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="text-sm font-medium text-muted-foreground">
                      AI Agents
                    </h3>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedRoom.agents?.map((agent, index) => {
                      const model = getModelInfo(agent.model_id)
                      return (
                        <button
                          key={agent.id}
                          onClick={() => handleViewModelDetails(agent.model_id)}
                          className="flex items-center gap-2 px-3 py-2 bg-muted/30 hover:bg-muted/50 rounded-lg border transition-colors group"
                          title={`${agent.display_name} - ${model?.name || agent.model_id}`}
                        >
                          <div className="relative">
                            <ModelIcon
                              modelName={model?.name || agent.model_id || ''}
                              modelId={agent.model_id || ''}
                              provider={model?.provider || ''}
                              modelIconSlug={model?.model_icon_slug}
                              modelIconUrl={model?.model_icon_url}
                              providerIconSlug={model?.provider_icon_slug}
                              providerIconUrl={model?.provider_icon_url}
                              size={24}
                              showTooltip={false}
                            />
                            <div className="absolute -bottom-1 -right-1 bg-background rounded-full px-1 text-[9px] font-medium border">
                              #{index + 1}
                            </div>
                          </div>
                          <div className="text-left">
                            <p className="text-sm font-medium leading-tight">{agent.display_name}</p>
                            <p className="text-[10px] text-muted-foreground leading-tight">
                              {agent.voice_name || 'Default voice'}
                            </p>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Conversation Transcript */}
                <div className="flex flex-col flex-1 min-h-0 overflow-hidden border rounded-lg bg-muted/10">
                  <div className="flex items-center justify-between px-3 md:px-4 py-2 border-b">
                    <h3 className="text-sm font-medium">Conversation History</h3>
                    {conversationMessages.length > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-muted-foreground hover:text-destructive"
                        onClick={() => setClearConversationDialogOpen(true)}
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        Clear
                      </Button>
                    )}
                  </div>
                  <ScrollArea className="flex-1">
                    <div className="p-3 md:p-4 space-y-3 md:space-y-4">
                      {conversationLoading ? (
                        <div className="flex flex-col items-center justify-center py-8 md:py-12">
                          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-accent-brand mb-3" />
                          <p className="text-sm text-muted-foreground">Loading conversation...</p>
                        </div>
                      ) : conversationMessages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-8 md:py-12 text-center">
                          <MessageSquare className="h-8 w-8 md:h-10 md:w-10 text-muted-foreground/30 mb-2 md:mb-3" />
                          <p className="text-sm text-muted-foreground">No conversation yet</p>
                          <p className="text-xs text-muted-foreground/70 mt-1">
                            Start a session to begin talking
                          </p>
                        </div>
                      ) : (
                        <>
                          {conversationMessages.map((message) => {
                            const isUser = message.role === 'user'
                            const agent = !isUser && message.agent_id
                              ? selectedRoom.agents?.find(a => a.id === message.agent_id)
                              : null
                            const agentModel = agent ? getModelInfo(agent.model_id) : null

                            return (
                              <div
                                key={message.id}
                                className={cn(
                                  'flex gap-3',
                                  isUser ? 'flex-row-reverse' : 'flex-row'
                                )}
                              >
                                {/* Avatar */}
                                {isUser ? (
                                  <Avatar className="h-8 w-8 shrink-0 bg-muted">
                                    {user?.avatar_url && (
                                      <AvatarImage
                                        src={user.avatar_url}
                                        alt={`${user.first_name || ''} ${user.last_name || ''}`}
                                      />
                                    )}
                                    <AvatarFallback className="bg-muted text-muted-foreground">
                                      <UserIcon className="h-4 w-4" />
                                    </AvatarFallback>
                                  </Avatar>
                                ) : (
                                  <div className="w-8 h-8 flex items-center justify-center shrink-0">
                                    {agentModel ? (
                                      <ModelIcon
                                        modelName={agentModel.name}
                                        modelId={agent?.model_id || ''}
                                        provider={agentModel.provider}
                                        modelIconSlug={agentModel.model_icon_slug}
                                        modelIconUrl={agentModel.model_icon_url}
                                        providerIconSlug={agentModel.provider_icon_slug}
                                        providerIconUrl={agentModel.provider_icon_url}
                                        size={32}
                                        showTooltip={false}
                                      />
                                    ) : (
                                      <ModelIcon
                                        modelName={message.agent_name || 'Assistant'}
                                        modelId=""
                                        provider=""
                                        size={32}
                                        showTooltip={false}
                                      />
                                    )}
                                  </div>
                                )}

                                {/* Message content */}
                                <div
                                  className={cn(
                                    'flex flex-col max-w-[85%] min-w-0',
                                    isUser ? 'items-end' : 'items-start'
                                  )}
                                >
                                  {/* Name and time */}
                                  <div
                                    className={cn(
                                      'flex items-center gap-2 mb-1',
                                      isUser ? 'flex-row-reverse' : 'flex-row'
                                    )}
                                  >
                                    <span className="text-xs font-medium">
                                      {isUser ? 'You' : (message.agent_name || agent?.display_name || 'Assistant')}
                                    </span>
                                    <span className="text-[10px] text-muted-foreground">
                                      {new Date(message.created_at).toLocaleTimeString([], {
                                        hour: '2-digit',
                                        minute: '2-digit',
                                      })}
                                    </span>
                                  </div>

                                  {/* Content bubble */}
                                  <div
                                    className={cn(
                                      'rounded-2xl px-4 py-2.5',
                                      isUser
                                        ? 'bg-primary/15 text-foreground rounded-tr-sm border border-primary/20'
                                        : 'bg-card text-foreground rounded-tl-sm'
                                    )}
                                  >
                                    {isUser ? (
                                      <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                                    ) : (
                                      <div className="prose prose-sm max-w-none prose-p:text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-code:text-primary">
                                        <Markdown>{message.content}</Markdown>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                          <div ref={conversationEndRef} />
                        </>
                      )}
                    </div>
                  </ScrollArea>
                </div>

                {/* Room Settings Footer */}
                <div className="mt-4 md:mt-6 pt-3 md:pt-4 border-t">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Settings2 className="h-3.5 w-3.5" />
                    <span>Created {new Date(selectedRoom.created_at).toLocaleDateString()}</span>
                    {selectedRoom.updated_at !== selectedRoom.created_at && (
                      <>
                        <span>•</span>
                        <span>Updated {new Date(selectedRoom.updated_at).toLocaleDateString()}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Empty State - Matching CodePage structure exactly */
            <div className="flex-1 flex flex-col relative overflow-hidden">
              {/* Ambient background gradient */}
              <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div
                  className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 w-[200vw] aspect-[2/1] rounded-[50%]"
                  style={{
                    background: 'radial-gradient(ellipse at center, hsl(var(--accent-brand)) 0%, transparent 70%)',
                    opacity: 'var(--glow-opacity, 0.2)'
                  }}
                />
              </div>

              {/* Mobile sticky header with menu and rooms dropdown */}
              <div className="md:hidden flex items-center gap-2 px-3 py-2 border-b border-border/50 bg-background/95 backdrop-blur-sm shrink-0 z-20">
                {/* Menu button */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={openMobileSidebar}
                >
                  <PremiumMenuIcon className="h-4 w-4" />
                </Button>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 px-2 gap-1.5 text-xs"
                    >
                      <Mic className="h-3.5 w-3.5" />
                      <span>Rooms</span>
                      <ChevronDown className="h-3 w-3 opacity-50" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-64 max-h-[300px] overflow-y-auto">
                    {roomsLoading ? (
                      <div className="flex items-center justify-center py-4">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent-brand" />
                      </div>
                    ) : rooms.length === 0 ? (
                      <div className="px-3 py-4 text-center text-xs text-muted-foreground">No rooms yet</div>
                    ) : (
                      rooms.slice(0, 10).map((room) => (
                        <div
                          key={room.id}
                          className="flex items-center gap-1 px-2 py-2 hover:bg-muted rounded-sm cursor-pointer"
                          onClick={() => setSelectedRoom(room)}
                        >
                          <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                            <span className="text-sm font-medium truncate">{room.name}</span>
                            <span className="text-xs text-muted-foreground truncate">
                              {room.agents?.length || 0} agent{(room.agents?.length || 0) !== 1 ? 's' : ''}
                            </span>
                          </div>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <button
                                className="flex-shrink-0 p-1 rounded hover:bg-muted-foreground/20"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
                              </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-36">
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleEditRoom(room)
                                }}
                              >
                                <Pencil className="h-3.5 w-3.5 mr-2" />
                                Edit
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleDeleteRoom(room)
                                }}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="h-3.5 w-3.5 mr-2" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      ))
                    )}
                    {rooms.length > 10 && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-xs text-muted-foreground">
                          {rooms.length} rooms total
                        </DropdownMenuItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              {/* Main content - positioned higher on screen */}
              <div className="flex-1 flex flex-col justify-center px-4 pb-6 pt-4 relative z-10 min-h-0 -translate-y-8 sm:-translate-y-12">
                <div className="max-w-2xl mx-auto w-full space-y-6 text-center">
                  {/* Mic icon */}
                  <div className="flex justify-center">
                    <div className="h-12 w-12 rounded-2xl bg-accent-brand/10 flex items-center justify-center border border-accent-brand/20">
                      <Mic className="h-6 w-6 text-accent-brand" />
                    </div>
                  </div>

                  {/* Title and subtitle */}
                  <div className="space-y-3">
                    <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground">
                      Who do you want to talk to?
                    </h1>
                    <p className="text-base text-muted-foreground">
                      Multi-AI voice conversations
                    </p>
                  </div>

                  {/* Create Room button */}
                  <div className="pt-2">
                    <Button
                      onClick={() => {
                        setSelectedPreset(null)
                        setIsCreateModalOpen(true)
                      }}
                      variant="outline"
                      className="h-11 px-6 text-sm rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300 transition-all"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Create Voice Room
                    </Button>
                  </div>

                  {/* Quick presets - premium styled chips, hidden on mobile */}
                  <div className="hidden sm:flex flex-col items-center gap-3 pt-4">
                    <span className="text-xs text-muted-foreground/50 uppercase tracking-wider font-medium">Or try a preset</span>
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      {suggestions.map((suggestion) => {
                        const Icon = suggestion.icon
                        return (
                          <button
                            key={suggestion.presetKey}
                            onClick={() => {
                              setSelectedPreset(ROOM_PRESETS[suggestion.presetKey])
                              setIsCreateModalOpen(true)
                            }}
                            className="group flex items-center gap-2 px-4 py-2 rounded-full bg-muted border border-border hover:bg-accent-brand/10 hover:border-accent-brand/30 transition-all duration-200"
                          >
                            <Icon className="h-4 w-4 text-muted-foreground group-hover:text-accent-brand transition-colors" />
                            <span className="text-sm text-muted-foreground group-hover:text-foreground transition-colors">{suggestion.title}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
      </div>

      {/* Create Room Modal */}
      <CreateRoomModal
        isOpen={isCreateModalOpen}
        onClose={() => {
          setIsCreateModalOpen(false)
          setSelectedPreset(null)
        }}
        onCreated={handleRoomCreated}
        preset={selectedPreset}
      />

      {/* Edit Room Modal */}
      <CreateRoomModal
        isOpen={isEditModalOpen}
        onClose={() => {
          setIsEditModalOpen(false)
          setRoomToEdit(null)
        }}
        onCreated={handleRoomUpdated}
        roomToEdit={roomToEdit}
      />

      {/* Model Details Modal */}
      <ModelDetailsModal
        isOpen={detailsModalOpen}
        onClose={() => setDetailsModalOpen(false)}
        model={selectedModelForDetails}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setDeleteDialogOpen(false)
            setRoomToDelete(null)
          }
        }}
        onConfirm={confirmDeleteRoom}
        title="Delete Voice Room"
        description={`Are you sure you want to delete "${roomToDelete?.name}"? This action cannot be undone.`}
        confirmText="Delete"
        cancelText="Cancel"
        variant="destructive"
        isLoading={isDeleting}
      />

      {/* Clear Conversation Confirmation Dialog */}
      <ConfirmDialog
        open={clearConversationDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setClearConversationDialogOpen(false)
          }
        }}
        onConfirm={handleClearConversation}
        title="Clear Conversation"
        description="Are you sure you want to clear the conversation history? This will start a fresh session."
        confirmText="Clear"
        cancelText="Cancel"
        variant="destructive"
        isLoading={isClearingConversation}
      />
    </div>
  )
}
