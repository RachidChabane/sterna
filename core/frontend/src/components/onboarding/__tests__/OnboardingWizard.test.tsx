import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { OnboardingWizard } from '../OnboardingWizard';
import { useOnboardingStore } from '@/store/onboardingStore';
import { useOnboardingTierStore } from '../onboardingTierStore';
import { useNavigate } from '@tanstack/react-router';

// Mock the router
vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn(),
}));

// Mock the API client completely: besides `api`, the onboarding store's
// preferencesSync (src/lib/preferencesSync.ts) and preferencesClient import
// getAccessToken/handleUnauthorized from it. getAccessToken returns null so
// preference sync short-circuits (unauthenticated) instead of hitting the network.
vi.mock('@/api/client', () => {
  const api = {
    post: vi.fn(),
    get: vi.fn(),
  };
  return {
    api,
    default: api,
    getAccessToken: vi.fn(() => null),
    getRefreshToken: vi.fn(() => null),
    setTokens: vi.fn(),
    clearTokens: vi.fn(),
    handleUnauthorized: vi.fn(),
    ORCHESTRATOR_URL: '/api/v1/sandbox',
  };
});

// Mock confetti
vi.mock('canvas-confetti', () => ({
  default: vi.fn(),
}));

// The wizard currently has 4 steps: welcome, api-key, sample-evaluation, success
// (model-intro / model-selection / cost-estimation were removed from the store
// flow; the tier selection now lives in onboardingTierStore).
const STEP_COUNT = 4;

describe('OnboardingWizard', () => {
  const mockNavigate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useNavigate).mockReturnValue(mockNavigate);

    // Reset the onboarding stores
    useOnboardingStore.setState({
      currentStep: 0,
      steps: useOnboardingStore.getState().steps.map(s => ({ ...s, completed: false })),
      onboardingCompleted: false,
      apiKeyConfigured: false,
      sampleEvaluationRun: false,
      skippedAt: null,
    });
    useOnboardingTierStore.setState({ selectedModelTier: null });
  });

  it('renders the welcome step initially', () => {
    render(<OnboardingWizard />);

    // The step title renders both in the wizard header (h1) and in the step body (h2)
    expect(
      screen.getByRole('heading', { level: 1, name: 'Welcome to Sterna' })
    ).toBeInTheDocument();
    expect(screen.getByText('Get Started')).toBeInTheDocument();
  });

  it('shows progress bar with correct percentage', () => {
    render(<OnboardingWizard />);

    // 4 steps -> first step is 25% complete
    expect(screen.getByText(`Step 1 of ${STEP_COUNT}`)).toBeInTheDocument();
    expect(screen.getByText(/25% Complete/)).toBeInTheDocument();
  });

  it('navigates to next step when clicking Next', async () => {
    render(<OnboardingWizard />);

    const getStartedButton = screen.getByText('Get Started');
    fireEvent.click(getStartedButton);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: 'Configure OpenRouter API' })
      ).toBeInTheDocument();
    });
  });

  it('navigates to previous step when clicking Previous', async () => {
    render(<OnboardingWizard />);

    // Go to second step
    const getStartedButton = screen.getByText('Get Started');
    fireEvent.click(getStartedButton);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: 'Configure OpenRouter API' })
      ).toBeInTheDocument();
    });

    // Go back
    const previousButton = screen.getByRole('button', { name: /previous/i });
    fireEvent.click(previousButton);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: 'Welcome to Sterna' })
      ).toBeInTheDocument();
    });
  });

  it('shows skip confirmation dialog', async () => {
    window.confirm = vi.fn(() => false);
    render(<OnboardingWizard />);

    const skipButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(skipButton);

    expect(window.confirm).toHaveBeenCalledWith(
      'Are you sure you want to skip the onboarding? You can restart it later from settings.'
    );
    // Declined: onboarding must not be marked complete
    expect(useOnboardingStore.getState().onboardingCompleted).toBe(false);
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('skips onboarding when confirmed', async () => {
    window.confirm = vi.fn(() => true);
    render(<OnboardingWizard />);

    const skipButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(skipButton);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({ to: '/voice-rooms' });
    });
    expect(useOnboardingStore.getState().onboardingCompleted).toBe(true);
    expect(useOnboardingStore.getState().skippedAt).toBeTruthy();
  });

  it('redirects to home when onboarding is completed', () => {
    useOnboardingStore.setState({ onboardingCompleted: true });

    render(<OnboardingWizard />);

    expect(mockNavigate).toHaveBeenCalledWith({ to: '/voice-rooms' });
  });

  it('displays all step indicators', () => {
    render(<OnboardingWizard />);

    const indicators = screen.getAllByRole('button', { name: /Go to/i });
    expect(indicators).toHaveLength(STEP_COUNT); // welcome, api-key, sample-evaluation, success
  });

  it('disables Next button when requirements are not met', async () => {
    render(<OnboardingWizard />);

    // Navigate to API key step
    fireEvent.click(screen.getByText('Get Started'));

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: 'Configure OpenRouter API' })
      ).toBeInTheDocument();
    });

    // Next button should be disabled without a configured API key
    const nextButton = screen.getByRole('button', { name: /next/i });
    expect(nextButton).toBeDisabled();
  });
});

describe('OnboardingStore', () => {
  beforeEach(() => {
    useOnboardingStore.setState({
      currentStep: 0,
      steps: useOnboardingStore.getState().steps.map(s => ({ ...s, completed: false })),
      apiKeyConfigured: false,
      sampleEvaluationRun: false,
      onboardingCompleted: false,
      skippedAt: null,
    });
    useOnboardingTierStore.setState({ selectedModelTier: null });
  });

  it('completes step when completeStep is called', () => {
    const { completeStep } = useOnboardingStore.getState();

    completeStep('welcome');

    const updatedSteps = useOnboardingStore.getState().steps;
    const welcomeStep = updatedSteps.find(s => s.id === 'welcome');
    expect(welcomeStep?.completed).toBe(true);
  });

  it('sets API key configuration status', () => {
    const { setApiKeyConfigured } = useOnboardingStore.getState();

    setApiKeyConfigured(true);

    expect(useOnboardingStore.getState().apiKeyConfigured).toBe(true);
    expect(useOnboardingStore.getState().steps.find(s => s.id === 'api-key')?.completed).toBe(true);
  });

  it('sets sample evaluation run status', () => {
    const { setSampleEvaluationRun } = useOnboardingStore.getState();

    setSampleEvaluationRun(true);

    expect(useOnboardingStore.getState().sampleEvaluationRun).toBe(true);
    expect(
      useOnboardingStore.getState().steps.find(s => s.id === 'sample-evaluation')?.completed
    ).toBe(true);
  });

  // The selected model tier no longer lives in the onboarding store: it moved to
  // the local onboardingTierStore (src/components/onboarding/onboardingTierStore.ts).
  it('sets selected model tier in the tier store', () => {
    const { setSelectedModelTier } = useOnboardingTierStore.getState();

    setSelectedModelTier('balanced');

    expect(useOnboardingTierStore.getState().selectedModelTier).toBe('balanced');
  });

  it('resets onboarding state', () => {
    useOnboardingStore.setState({
      currentStep: 3,
      apiKeyConfigured: true,
      sampleEvaluationRun: true,
      onboardingCompleted: true,
    });

    const { resetOnboarding } = useOnboardingStore.getState();
    resetOnboarding();

    const state = useOnboardingStore.getState();
    expect(state.currentStep).toBe(0);
    expect(state.apiKeyConfigured).toBe(false);
    expect(state.sampleEvaluationRun).toBe(false);
    expect(state.onboardingCompleted).toBe(false);
    expect(state.skippedAt).toBe(null);
    expect(state.steps.every(s => !s.completed)).toBe(true);
  });

  it('skips onboarding with timestamp', () => {
    const { skipOnboarding } = useOnboardingStore.getState();

    skipOnboarding();

    const state = useOnboardingStore.getState();
    expect(state.onboardingCompleted).toBe(true);
    expect(state.skippedAt).toBeTruthy();
  });
});
