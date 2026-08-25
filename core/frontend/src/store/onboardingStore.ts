import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { createUserScopedStorage } from '../lib/userScopedStorage';
import { preferencesSync } from '../lib/preferencesSync';
import { PREFERENCE_KEYS } from '../hooks/usePreferencesLoader';

interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  completed: boolean;
}

interface OnboardingState {
  currentStep: number;
  steps: OnboardingStep[];
  apiKeyConfigured: boolean;
  sampleEvaluationRun: boolean;
  onboardingCompleted: boolean;
  skippedAt: string | null;

  // Actions
  setCurrentStep: (step: number) => void;
  completeStep: (stepId: string) => void;
  setApiKeyConfigured: (configured: boolean) => void;
  setSampleEvaluationRun: (run: boolean) => void;
  completeOnboarding: () => void;
  resetOnboarding: () => void;
  skipOnboarding: () => void;
}

const defaultSteps: OnboardingStep[] = [
  {
    id: 'welcome',
    title: 'Welcome to Sterna',
    description: 'Get started with AI-powered quality evaluation',
    completed: false,
  },
  {
    id: 'api-key',
    title: 'Configure OpenRouter API',
    description: 'Connect your OpenRouter account for model access',
    completed: false,
  },
  {
    id: 'sample-evaluation',
    title: 'Try a Sample Evaluation',
    description: 'Run your first evaluation with multiple models',
    completed: false,
  },
  {
    id: 'success',
    title: 'Setup Complete!',
    description: 'You\'re ready to start evaluating',
    completed: false,
  },
];

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      currentStep: 0,
      steps: defaultSteps,
      apiKeyConfigured: false,
      sampleEvaluationRun: false,
      onboardingCompleted: false,
      skippedAt: null,

      setCurrentStep: (step) => {
        set({ currentStep: step })

        // Sync to backend
        preferencesSync.update(PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP, step, 'onboarding')
      },

      completeStep: (stepId) =>
        set((state) => ({
          steps: state.steps.map((s) =>
            s.id === stepId ? { ...s, completed: true } : s
          ),
        })),

      setApiKeyConfigured: (configured) => {
        set((state) => {
          const newState = { apiKeyConfigured: configured };

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED, configured, 'onboarding')

          if (configured) {
            return {
              ...newState,
              steps: state.steps.map((s) =>
                s.id === 'api-key' ? { ...s, completed: true } : s
              ),
            };
          }
          return newState;
        })
      },

      setSampleEvaluationRun: (run) => {
        set((state) => {
          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN, run, 'onboarding')

          return {
            sampleEvaluationRun: run,
            steps: state.steps.map((s) =>
              s.id === 'sample-evaluation' ? { ...s, completed: true } : s
            ),
          }
        })
      },

      completeOnboarding: () => {
        set((state) => {
          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.ONBOARDING_COMPLETED, true, 'onboarding')

          return {
            onboardingCompleted: true,
            steps: state.steps.map((s) =>
              s.id === 'success' ? { ...s, completed: true } : s
            ),
          }
        })
      },

      resetOnboarding: () =>
        set({
          currentStep: 0,
          steps: defaultSteps,
          apiKeyConfigured: false,
          sampleEvaluationRun: false,
          onboardingCompleted: false,
          skippedAt: null,
        }),

      skipOnboarding: () => {
        const skippedAt = new Date().toISOString()

        set({
          onboardingCompleted: true,
          skippedAt,
        })

        // Sync to backend
        preferencesSync.update(PREFERENCE_KEYS.ONBOARDING_COMPLETED, true, 'onboarding')
        preferencesSync.update(PREFERENCE_KEYS.ONBOARDING_SKIPPED_AT, skippedAt, 'onboarding')
      },
    }),
    {
      name: 'onboarding-storage',
      storage: createUserScopedStorage('onboarding-storage'),
    }
  )
);