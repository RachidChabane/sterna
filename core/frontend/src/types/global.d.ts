// Global type declarations

// Google Sign-In
interface Window {
  google?: {
    accounts: {
      id: {
        initialize: (config: {
          client_id: string
          callback: (response: { credential?: string }) => void
        }) => void
        prompt: () => void
      }
    }
  }
}
