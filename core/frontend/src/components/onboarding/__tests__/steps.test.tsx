import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { WelcomeStep } from '../steps/WelcomeStep';
import { ApiKeyStep } from '../steps/ApiKeyStep';
import { ModelIntroStep } from '../steps/ModelIntroStep';
import { ModelSelectionStep } from '../steps/ModelSelectionStep';
import { CostEstimationStep } from '../steps/CostEstimationStep';
import { SampleEvaluationStep } from '../steps/SampleEvaluationStep';
import { SuccessStep } from '../steps/SuccessStep';
import { useOnboardingStore } from '@/store/onboardingStore';
import { useOnboardingTierStore } from '../onboardingTierStore';
import { api } from '@/api/client';
import { useNavigate } from '@tanstack/react-router';

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

vi.mock('@tanstack/react-router', () => ({
  useNavigate: vi.fn(() => vi.fn()),
}));

vi.mock('canvas-confetti', () => ({
  default: vi.fn(),
}));

vi.mock('@/hooks/use-toast', () => ({
  toast: vi.fn(),
  useToast: vi.fn(() => ({
    toast: vi.fn(),
  })),
}));

describe('WelcomeStep', () => {
  it('renders welcome content', () => {
    const onNext = vi.fn();
    render(<WelcomeStep onNext={onNext} />);

    expect(screen.getByText('Welcome to Sterna')).toBeInTheDocument();
    expect(screen.getByText(/Your AI-powered quality evaluation platform/)).toBeInTheDocument();
  });

  it('displays feature cards', () => {
    const onNext = vi.fn();
    render(<WelcomeStep onNext={onNext} />);

    expect(screen.getByText('Sterna')).toBeInTheDocument();
    expect(screen.getByText('Performance Metrics')).toBeInTheDocument();
    expect(screen.getByText('Team Collaboration')).toBeInTheDocument();
    expect(screen.getByText('100+ Models')).toBeInTheDocument();
  });

  it('calls onNext when Get Started is clicked', () => {
    const onNext = vi.fn();
    render(<WelcomeStep onNext={onNext} />);

    fireEvent.click(screen.getByText('Get Started'));
    expect(onNext).toHaveBeenCalled();
  });
});

describe('ApiKeyStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders API key setup content', () => {
    const onNext = vi.fn();
    render(<ApiKeyStep onNext={onNext} />);

    expect(screen.getByText('Configure OpenRouter API')).toBeInTheDocument();
    expect(screen.getByText('What is OpenRouter?')).toBeInTheDocument();
  });

  it('shows API key input field', () => {
    const onNext = vi.fn();
    render(<ApiKeyStep onNext={onNext} />);

    const input = screen.getByPlaceholderText('sk-or-v1-...');
    expect(input).toBeInTheDocument();
  });

  it('toggles API key visibility', () => {
    const onNext = vi.fn();
    render(<ApiKeyStep onNext={onNext} />);

    const input = screen.getByPlaceholderText('sk-or-v1-...') as HTMLInputElement;
    expect(input.type).toBe('password');

    // Find and click the eye icon button
    const toggleButton = screen.getAllByRole('button')[0];
    fireEvent.click(toggleButton);

    expect(input.type).toBe('text');
  });

  it('validates API key format', () => {
    const onNext = vi.fn();
    render(<ApiKeyStep onNext={onNext} />);

    const input = screen.getByPlaceholderText('sk-or-v1-...');
    fireEvent.change(input, { target: { value: 'invalid-key' } });

    expect(screen.getByText(/OpenRouter API keys typically start with/)).toBeInTheDocument();
  });

  it('tests API connection', async () => {
    const onNext = vi.fn();
    // Two calls on success: connection test, then saving the key to settings
    vi.mocked(api.post).mockResolvedValue({ data: { success: true } });

    render(<ApiKeyStep onNext={onNext} />);

    const input = screen.getByPlaceholderText('sk-or-v1-...');
    fireEvent.change(input, { target: { value: 'sk-or-v1-test' } });

    fireEvent.click(screen.getByText('Test Connection'));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/llm/models/test-connection/', {
        api_key: 'sk-or-v1-test',
      });
    });

    // On success, the key is persisted to settings and the step is marked done
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/settings/openrouter/', {
        api_key: 'sk-or-v1-test',
      });
    });
    expect(await screen.findByText('Continue')).toBeInTheDocument();
    expect(useOnboardingStore.getState().apiKeyConfigured).toBe(true);
  });
});

describe('ModelIntroStep', () => {
  it('renders model tier information', () => {
    const onNext = vi.fn();
    render(<ModelIntroStep onNext={onNext} />);

    expect(screen.getByText('Understanding Model Tiers')).toBeInTheDocument();
    expect(screen.getByText('Budget')).toBeInTheDocument();
    expect(screen.getByText('Balanced')).toBeInTheDocument();
    expect(screen.getByText('Quality')).toBeInTheDocument();
  });

  it('shows recommended tier badge', () => {
    const onNext = vi.fn();
    render(<ModelIntroStep onNext={onNext} />);

    expect(screen.getByText('RECOMMENDED')).toBeInTheDocument();
  });

  it('completes step when continuing', () => {
    const onNext = vi.fn();
    const completeStep = vi.fn();
    useOnboardingStore.setState({ completeStep });

    render(<ModelIntroStep onNext={onNext} />);

    fireEvent.click(screen.getByText('Continue to Model Selection'));

    expect(onNext).toHaveBeenCalled();
  });
});

describe('ModelSelectionStep', () => {
  beforeEach(() => {
    // The tier selection moved from the onboarding store to onboardingTierStore
    useOnboardingTierStore.setState({ selectedModelTier: null });
    useOnboardingStore.setState({ completeStep: vi.fn() });
  });

  it('renders tier selection options', () => {
    const onNext = vi.fn();
    render(<ModelSelectionStep onNext={onNext} />);

    expect(screen.getByText('Select Your Default Model Tier')).toBeInTheDocument();
    expect(screen.getByLabelText('Budget Tier')).toBeInTheDocument();
    expect(screen.getByLabelText('Balanced Tier')).toBeInTheDocument();
    expect(screen.getByLabelText('Quality Tier')).toBeInTheDocument();
  });

  it('selects a model tier', () => {
    const onNext = vi.fn();
    render(<ModelSelectionStep onNext={onNext} />);

    const balancedOption = screen.getByLabelText('Balanced Tier');
    fireEvent.click(balancedOption);

    expect(balancedOption).toBeChecked();
  });

  it('shows cost estimates', () => {
    const onNext = vi.fn();
    render(<ModelSelectionStep onNext={onNext} />);

    expect(screen.getByText('$10-50')).toBeInTheDocument();
    expect(screen.getByText('$50-200')).toBeInTheDocument();
    expect(screen.getByText('$200-1000+')).toBeInTheDocument();
  });
});

describe('CostEstimationStep', () => {
  it('renders cost calculator', () => {
    const onNext = vi.fn();
    render(<CostEstimationStep onNext={onNext} />);

    expect(screen.getByText('Cost Estimation & Optimization')).toBeInTheDocument();
    expect(screen.getByText('Your Usage Pattern')).toBeInTheDocument();
  });

  it('shows cost optimization tips', () => {
    const onNext = vi.fn();
    render(<CostEstimationStep onNext={onNext} />);

    expect(screen.getByText('Cost Optimization Tips')).toBeInTheDocument();
    expect(screen.getByText(/Use budget models for development/)).toBeInTheDocument();
  });

  it('displays cost comparison', () => {
    const onNext = vi.fn();
    render(<CostEstimationStep onNext={onNext} />);

    expect(screen.getByText('Cost Comparison by Tier')).toBeInTheDocument();
  });
});

describe('SampleEvaluationStep', () => {
  beforeEach(() => {
    useOnboardingTierStore.setState({ selectedModelTier: 'balanced' });
    useOnboardingStore.setState({
      setSampleEvaluationRun: vi.fn(),
      completeStep: vi.fn(),
    });
  });

  it('renders sample evaluation setup', () => {
    const onNext = vi.fn();
    render(<SampleEvaluationStep onNext={onNext} />);

    expect(screen.getByText('Try a Sample Evaluation')).toBeInTheDocument();
    expect(screen.getByText('Sample Task: Code Generation')).toBeInTheDocument();
  });

  it('shows evaluation criteria', () => {
    const onNext = vi.fn();
    render(<SampleEvaluationStep onNext={onNext} />);

    expect(screen.getByText('Correctness')).toBeInTheDocument();
    expect(screen.getByText('Efficiency')).toBeInTheDocument();
    expect(screen.getByText('Code Quality')).toBeInTheDocument();
  });

  it('runs sample evaluation', async () => {
    const onNext = vi.fn();
    vi.mocked(api.post).mockResolvedValueOnce({
      data: {
        score: 85,
        latency: 1500,
        cost: 0.005,
        passed: true,
      },
    });

    render(<SampleEvaluationStep onNext={onNext} />);

    fireEvent.click(screen.getByText('Run Sample Evaluation'));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/api/evaluations/sample/',
        expect.any(Object)
      );
    });
  });
});

describe('SuccessStep', () => {
  it('renders success message', () => {
    render(<SuccessStep />);

    expect(screen.getByText('Congratulations!')).toBeInTheDocument();
    expect(screen.getByText(/You're all set up/)).toBeInTheDocument();
  });

  it('shows accomplishments', () => {
    render(<SuccessStep />);

    expect(screen.getByText('What You\'ve Accomplished')).toBeInTheDocument();
    expect(screen.getByText('Connected OpenRouter API')).toBeInTheDocument();
    expect(screen.getByText('Selected optimal model tier')).toBeInTheDocument();
  });

  it('displays quick actions', () => {
    render(<SuccessStep />);

    expect(screen.getByText('Start Chatting')).toBeInTheDocument();
    expect(screen.getByText('Compare Models')).toBeInTheDocument();
    expect(screen.getByText('Connect a Tool')).toBeInTheDocument();
    expect(screen.getByText('Build a Knowledge Base')).toBeInTheDocument();
  });

  it('navigates to chats and completes onboarding', () => {
    const mockNavigate = vi.fn();
    vi.mocked(useNavigate).mockReturnValue(mockNavigate);
    useOnboardingStore.setState({ onboardingCompleted: false });

    render(<SuccessStep />);

    fireEvent.click(screen.getByText('Get Started'));

    expect(mockNavigate).toHaveBeenCalledWith({ to: '/chats' });
    expect(useOnboardingStore.getState().onboardingCompleted).toBe(true);
  });
});