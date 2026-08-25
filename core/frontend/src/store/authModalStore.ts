import { create } from 'zustand'

type AuthModalVariant = 'session-expired' | 'sign-up-prompt'

interface AuthModalState {
  isOpen: boolean
  variant: AuthModalVariant
  returnUrl: string | null
  isRedirecting: boolean
  openModal: (variant: AuthModalVariant, returnUrl?: string) => void
  closeModal: () => void
  setReturnUrl: (url: string | null) => void
  setRedirecting: (isRedirecting: boolean) => void
}

/**
 * Store for managing authentication modal state globally.
 * Used to show contextual auth prompts instead of redirecting to login page.
 */
export const useAuthModalStore = create<AuthModalState>((set) => ({
  isOpen: false,
  variant: 'session-expired',
  returnUrl: null,
  isRedirecting: false,

  /**
   * Opens the authentication modal with the specified variant
   * @param variant - Type of modal to show ('session-expired' | 'sign-up-prompt')
   * @param returnUrl - Optional URL to redirect to after successful authentication
   */
  openModal: (variant, returnUrl) => {
    
    set({
      isOpen: true,
      variant,
      returnUrl: returnUrl || null,
    })
  },

  /**
   * Closes the authentication modal
   */
  closeModal: () => {
    
    set({ isOpen: false })
  },

  /**
   * Updates the return URL without opening the modal
   * @param url - URL to redirect to after authentication
   */
  setReturnUrl: (url) => {
    set({ returnUrl: url })
  },

  /**
   * Sets the redirecting state to prevent modal from reopening during navigation
   * @param isRedirecting - Whether we're currently redirecting after modal close
   */
  setRedirecting: (isRedirecting) => {
    set({ isRedirecting })
  },
}))
