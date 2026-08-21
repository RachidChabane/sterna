import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { authApi } from '@/api/endpoints'
import { CONSENT_POLICY_VERSION } from '@/components/consent/policyVersion'
import type { ConsentCategories, ConsentRegionDefault } from '@/api/types'

export interface ConsentStore {
  sessionId: string | null
  categories: ConsentCategories
  version: string
  regionDefault: ConsentRegionDefault
  hasDecided: boolean
  isBannerOpen: boolean
  isDialogOpen: boolean

  initialize: () => Promise<void>
  openDialog: () => void
  closeDialog: () => void
  acceptAll: () => Promise<void>
  rejectAll: () => Promise<void>
  saveCategories: (categories: ConsentCategories) => Promise<void>
  setCategory: (key: keyof ConsentCategories, value: boolean) => Promise<void>
  attachToCurrentUser: () => Promise<void>
}

const DEFAULT_CATEGORIES: ConsentCategories = {
  essential: true,
  analytics: false,
  marketing: false,
}

function mintSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export const useConsentStore = create<ConsentStore>()(
  persist(
    (set, get) => ({
      sessionId: null,
      categories: DEFAULT_CATEGORIES,
      version: '',
      regionDefault: 'unknown',
      hasDecided: false,
      isBannerOpen: false,
      isDialogOpen: false,

      initialize: async () => {
        const state = get()
        if (state.hasDecided && state.version === CONSENT_POLICY_VERSION) {
          return
        }

        const sessionId = state.sessionId ?? mintSessionId()
        try {
          const { data } = await authApi.consent.get(sessionId)
          if (data.consent && data.consent.version === CONSENT_POLICY_VERSION) {
            set({
              sessionId,
              categories: data.consent.categories,
              version: data.consent.version,
              regionDefault: data.region_default,
              hasDecided: true,
              isBannerOpen: false,
            })
            return
          }
          const preChecked: ConsentCategories = {
            essential: true,
            analytics: data.region_default !== 'EU',
            marketing: false,
          }
          set({
            sessionId,
            categories: preChecked,
            version: '',
            regionDefault: data.region_default,
            hasDecided: false,
            isBannerOpen: true,
          })
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error('[consent] initialize failed', err)
          set({
            sessionId,
            categories: DEFAULT_CATEGORIES,
            version: '',
            regionDefault: 'EU',
            hasDecided: false,
            isBannerOpen: true,
          })
        }
      },

      openDialog: () => set({ isDialogOpen: true }),
      closeDialog: () => set({ isDialogOpen: false }),

      acceptAll: async () => {
        await get().saveCategories({
          essential: true,
          analytics: true,
          marketing: true,
        })
      },

      rejectAll: async () => {
        await get().saveCategories({
          essential: true,
          analytics: false,
          marketing: false,
        })
      },

      saveCategories: async (categories) => {
        const sessionId = get().sessionId ?? mintSessionId()
        const safe: ConsentCategories = { ...categories, essential: true }
        try {
          await authApi.consent.save({
            session_id: sessionId,
            categories: safe,
            version: CONSENT_POLICY_VERSION,
          })
          set({
            sessionId,
            categories: safe,
            version: CONSENT_POLICY_VERSION,
            hasDecided: true,
            isBannerOpen: false,
            isDialogOpen: false,
          })
        } catch (err) {
          set({
            sessionId,
            categories: safe,
            hasDecided: false,
            isBannerOpen: true,
          })
          throw err
        }
      },

      setCategory: async (key, value) => {
        const next = { ...get().categories, [key]: value }
        await get().saveCategories(next)
      },

      attachToCurrentUser: async () => {
        const sessionId = get().sessionId
        if (!sessionId) return
        try {
          await authApi.consent.attach(sessionId)
        } catch {
          // Non-fatal — the user is logged in; the row stays queryable by session_id.
        }
      },
    }),
    {
      name: 'consent-storage',
      partialize: (state) => ({
        sessionId: state.sessionId,
        categories: state.categories,
        version: state.version,
        regionDefault: state.regionDefault,
        hasDecided: state.hasDecided,
      }),
    },
  ),
)
