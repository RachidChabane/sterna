import { createFileRoute, redirect } from '@tanstack/react-router';
import { OnboardingWizard } from '@/components/onboarding/OnboardingWizard';
import { useOnboardingStore } from '@/store/onboardingStore';

export const Route = createFileRoute('/onboarding')({
  beforeLoad: async () => {
    // Check if onboarding is already completed
    const { onboardingCompleted } = useOnboardingStore.getState();
    if (onboardingCompleted) {
      throw redirect({
        to: '/chats',
      });
    }
  },
  component: OnboardingPage,
});

function OnboardingPage() {
  return <OnboardingWizard />;
}