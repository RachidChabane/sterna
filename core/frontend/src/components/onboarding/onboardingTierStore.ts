import { create } from 'zustand';

/**
 * Model tier selection made during onboarding.
 *
 * The canonical onboarding store (src/store/onboardingStore.ts) no longer
 * tracks the selected model tier, so the tier chosen in ModelSelectionStep
 * and displayed in CostEstimationStep lives in this local store instead.
 */
type OnboardingModelTier = 'budget' | 'balanced' | 'quality';

interface OnboardingTierState {
  selectedModelTier: OnboardingModelTier | null;
  setSelectedModelTier: (tier: OnboardingModelTier) => void;
}

export const useOnboardingTierStore = create<OnboardingTierState>()((set) => ({
  selectedModelTier: null,
  setSelectedModelTier: (tier) => set({ selectedModelTier: tier }),
}));
