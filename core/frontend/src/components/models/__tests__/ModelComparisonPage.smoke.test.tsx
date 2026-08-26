/**
 * Smoke test: pins which top-level branch ModelComparisonPage renders for a
 * representative set of conversation states. Every custom hook, store, and
 * heavy child view is stubbed so the test exercises only the container's own
 * branch-selection logic (loading / new-conversation / loading-skeleton /
 * immersive-single / immersive-multi / grid).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import '@testing-library/jest-dom'
import type { Chat, ChatGroup } from '../types'

// ---- router ---------------------------------------------------------------
const searchParams: { conversation?: string; new?: boolean; fix_spark?: string; fix_error?: string; ignite?: string } = {}
const navigateMock = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useSearch: () => searchParams,
  useNavigate: () => navigateMock,
}))

// ---- stores -----------------------------------------------------------------
vi.mock('@/store/modelStore', () => ({
  default: (selector: (s: unknown) => unknown) => selector({ currentModel: null, setCurrentModel: vi.fn(), recentChatModels: [] }),
}))
vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (s: unknown) => unknown) => selector({ isAuthenticated: true }),
}))
vi.mock('@/store/authModalStore', () => ({
  useAuthModalStore: (selector: (s: unknown) => unknown) => selector({ openModal: vi.fn() }),
}))
vi.mock('@/store/consigliereStore', () => ({
  useConsigliereStore: (selector: (s: unknown) => unknown) => selector({ openConsigliere: vi.fn() }),
}))
vi.mock('@/store/mcpStore', () => ({
  useMCPStore: (selector: (s: unknown) => unknown) => selector({ getActiveServers: vi.fn(() => []), fetchServers: vi.fn(), servers: [] }),
}))
vi.mock('@/store/activeConversationStore', () => ({
  useActiveConversationStore: (selector: (s: unknown) => unknown) => selector({ setActiveConversationId: vi.fn() }),
}))
vi.mock('@/store/artifactsPanelStore', () => ({
  useArtifactsPanelStore: (selector: (s: unknown) => unknown) => selector({}),
}))

// ---- API modules ------------------------------------------------------------
vi.mock('@/api/llm', () => ({
  llmApi: { models: vi.fn().mockResolvedValue({ data: { count: 0, results: [] } }) },
}))
vi.mock('@/api/assets', () => ({
  assetsAPI: { uploadFile: vi.fn() },
  assetToReference: vi.fn(),
  getAssetTypeFromMime: vi.fn(),
}))
vi.mock('@/api/conversations', () => ({
  conversationsAPI: { deleteMessage: vi.fn() },
}))
vi.mock('@/api/sparks', () => ({
  sparksAPI: {},
}))
vi.mock('@/lib/preferencesSync', () => ({
  preferencesSync: { get: vi.fn().mockResolvedValue(null), update: vi.fn() },
}))
vi.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

// ---- feature/composition hooks ----------------------------------------------
const featureState = { enabled: 0, total: 0, supported: 0 }
vi.mock('@/hooks/useGlobalFeatureToggles', () => ({
  useGlobalFeatureToggles: () => ({
    getWebSearchState: () => featureState,
    toggleWebSearch: vi.fn(),
    hasWebSearchSupport: () => false,
    hasReasoningSupport: () => false,
    getReasoningState: () => featureState,
    toggleReasoning: vi.fn(),
    getMCPToolsState: () => featureState,
    toggleMCPTools: vi.fn(),
    hasFunctionSupport: () => false,
    getFileToolsState: () => featureState,
    toggleFileTools: vi.fn(),
    getImageGenerationState: () => featureState,
    toggleImageGeneration: vi.fn(),
    getVideoGenerationState: () => featureState,
    toggleVideoGeneration: vi.fn(),
    getSparksState: () => featureState,
    toggleSparks: vi.fn(),
    getKnowledgeBaseState: () => featureState,
    toggleKnowledgeBase: vi.fn(),
    hasKnowledgeBaseSupport: () => false,
  }),
}))
vi.mock('@/hooks/useAttachmentManagement', () => ({
  useAttachmentManagement: () => ({ attachments: [], setAttachments: vi.fn(), addAttachments: vi.fn() }),
}))
vi.mock('@/hooks/useComparisonInput', () => ({
  useComparisonInput: () => ({
    sharedInput: '',
    setSharedInput: vi.fn(),
    sharedInputRef: { current: null },
    isDropOverInput: false,
    handleSharedDragOver: vi.fn(),
    handleSharedDragLeave: vi.fn(),
    handleSharedDrop: vi.fn(),
    handleSharedPaste: vi.fn(),
    handleKeyDown: vi.fn(),
    clearInput: vi.fn(),
  }),
}))
vi.mock('@/hooks/useCostEstimation', () => ({
  useCostEstimation: () => ({ estimatedCosts: {}, loadingEstimate: {}, setEstimatedCosts: vi.fn() }),
}))
vi.mock('@/hooks/useComparisonHelpers', () => ({
  useComparisonHelpers: () => ({
    generateFullGroupName: vi.fn(),
    generateGroupName: vi.fn(),
    hasMessages: vi.fn(() => false),
    hasVisionSupport: vi.fn(() => false),
    hasPDFSupport: vi.fn(() => false),
    getTotalTokens: vi.fn(() => 0),
  }),
}))
vi.mock('@/hooks/useChatManagement', () => ({
  useChatManagement: () => ({
    addChat: vi.fn(),
    removeChat: vi.fn(),
    clearChat: vi.fn(),
    updateChat: vi.fn(),
    updateChatModel: vi.fn(),
    updateChatMessages: vi.fn(),
    updateChatParameters: vi.fn(),
    updateChatDisabled: vi.fn(),
    updateChatHidden: vi.fn(),
    applyParametersToAllChats: vi.fn(),
    moveLeft: vi.fn(),
    moveRight: vi.fn(),
  }),
}))
vi.mock('@/hooks/useMessageSending', () => ({
  useMessageSending: () => ({
    sendToModel: vi.fn(),
    composeAndSend: vi.fn(),
    sendSparkFixMessage: vi.fn(),
    sendIgniteMessage: vi.fn(),
    abortControllersRef: { current: new Map() },
  }),
}))
vi.mock('@/hooks/useMultiChatTabState', () => ({
  useMultiChatTabState: () => ({ activeTabId: null, setActiveTabId: vi.fn(), seenResponseCounts: {} }),
}))
vi.mock('@/hooks/useModelFilters', () => ({
  useModelFilters: () => ({
    showFilters: false,
    setShowFilters: vi.fn(),
    filters: { input_modalities: [] },
    setFilters: vi.fn(),
    providers: [],
    filteredModels: [],
    hasActiveFilters: () => false,
  }),
}))

// ---- useConversations (varies per test) -------------------------------------
const useConversationsMock = vi.fn()
vi.mock('@/hooks/useConversations', () => ({
  useConversations: () => useConversationsMock(),
}))

// ---- heavy child views: stub with identifiable testids -----------------------
vi.mock('../ImmersiveChatView', () => ({
  ImmersiveChatView: ({ chat }: { chat: Chat }) => (
    <div data-testid="stub-immersive-chat-view" data-chat-id={chat.id} />
  ),
}))
vi.mock('../ChatTabContainer', () => ({
  ChatTabContainer: ({ chats }: { chats: Chat[] }) => (
    <div data-testid="stub-chat-tab-container" data-chat-count={chats.length} />
  ),
}))
vi.mock('../ChatGrid', () => ({
  ChatGrid: ({ chats }: { chats: Chat[] }) => (
    <div data-testid="stub-chat-grid" data-chat-count={chats.length} />
  ),
}))
vi.mock('../ChatInstructionsSheet', () => ({
  ChatInstructionsSheet: () => <div data-testid="stub-chat-instructions-sheet" />,
}))
vi.mock('../ArtifactsSidePanel', () => ({
  ArtifactsSidePanel: () => <div data-testid="stub-artifacts-side-panel" />,
}))
vi.mock('../ConversationsModal', () => ({
  ConversationsModal: () => <div data-testid="stub-conversations-modal" />,
}))
vi.mock('@/components/shared', () => ({
  ConfirmDeleteModal: () => <div data-testid="stub-confirm-delete-modal" />,
}))
vi.mock('@/components/consigliere/ConsigliereModal', () => ({
  ConsigliereModal: () => <div data-testid="stub-consigliere-modal" />,
}))
vi.mock('../SuggestedQuestionsCarousel', () => ({
  SuggestedQuestionsCarousel: () => <div data-testid="stub-suggested-questions-carousel" />,
}))
vi.mock('../CostEstimationDisplay', () => ({
  CostEstimationDisplay: () => <div data-testid="stub-cost-estimation-display" />,
}))

// eslint-disable-next-line import/first -- mocks above must register before the container import
import ModelComparisonPage from '../ModelComparisonPage'

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return {
    id: 'chat-1',
    model: null,
    messages: [],
    isLoading: false,
    parameters: {} as Chat['parameters'],
    ...overrides,
  }
}

function makeGroup(chats: Chat[], overrides: Partial<ChatGroup> = {}): ChatGroup {
  return {
    id: 'group-1',
    name: 'Group 1',
    chats,
    updatedAt: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  } as ChatGroup
}

function setConversationsState(overrides: Partial<ReturnType<typeof baseConversationsState>>) {
  useConversationsMock.mockReturnValue({ ...baseConversationsState(), ...overrides })
}

function baseConversationsState() {
  return {
    chatGroups: [] as ChatGroup[],
    setChatGroups: vi.fn(),
    isLoading: false,
    createConversation: vi.fn(),
    loadConversation: vi.fn(),
    deleteConversation: vi.fn(),
    clearConversation: vi.fn(),
    renameConversation: vi.fn(),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  searchParams.conversation = undefined
  searchParams.new = undefined
  searchParams.fix_spark = undefined
  searchParams.fix_error = undefined
  searchParams.ignite = undefined
  try {
    window.localStorage.clear()
    window.sessionStorage.clear()
  } catch {
    // storage unavailable in this environment - nothing to clear
  }
})

// Lets the fetchModels()/fetchServers() mount effects settle so their
// state updates land inside act() instead of after the test returns.
async function flushMountEffects() {
  await act(async () => {
    await Promise.resolve()
  })
}

describe('ModelComparisonPage — branch selection', () => {
  it('renders nothing while conversations are still loading', async () => {
    setConversationsState({ isLoading: true })
    const { container } = render(<ModelComparisonPage />)
    await flushMountEffects()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the new-conversation immersive view when ?new=true', async () => {
    searchParams.new = true
    setConversationsState({})
    render(<ModelComparisonPage />)
    await flushMountEffects()
    expect(screen.getByTestId('stub-immersive-chat-view')).toHaveAttribute('data-chat-id', 'new-conversation-temp')
  })

  it('renders the loading skeleton when the active group has no chats loaded yet', async () => {
    searchParams.conversation = 'group-1'
    setConversationsState({ chatGroups: [makeGroup([])] })
    const { container } = render(<ModelComparisonPage />)
    await waitFor(() => {
      expect(container.querySelector('[class*="animate-pulse"]')).toBeTruthy()
    })
    expect(screen.queryByTestId('stub-immersive-chat-view')).not.toBeInTheDocument()
    expect(screen.queryByTestId('stub-chat-grid')).not.toBeInTheDocument()
  })

  it('renders the single-chat immersive view for one chat in immersive mode', async () => {
    searchParams.conversation = 'group-1'
    setConversationsState({ chatGroups: [makeGroup([makeChat({ id: 'chat-solo' })])] })
    render(<ModelComparisonPage />)
    expect(await screen.findByTestId('stub-immersive-chat-view')).toHaveAttribute('data-chat-id', 'chat-solo')
  })

  it('renders the multi-chat tab container for several chats in immersive mode', async () => {
    searchParams.conversation = 'group-1'
    setConversationsState({
      chatGroups: [makeGroup([makeChat({ id: 'chat-a' }), makeChat({ id: 'chat-b' })])],
    })
    render(<ModelComparisonPage />)
    expect(await screen.findByTestId('stub-chat-tab-container')).toHaveAttribute('data-chat-count', '2')
  })

  it('renders the grid view for multiple chats outside immersive mode', async () => {
    searchParams.conversation = 'group-1'
    setConversationsState({
      chatGroups: [makeGroup([makeChat({ id: 'chat-a' }), makeChat({ id: 'chat-b' })])],
    })
    try {
      window.localStorage.setItem('models.immersive_mode.group-1', JSON.stringify(false))
    } catch {
      // localStorage unavailable - immersive mode falls back to its default
    }
    render(<ModelComparisonPage />)
    expect(await screen.findByTestId('stub-chat-grid')).toHaveAttribute('data-chat-count', '2')
  })
})
