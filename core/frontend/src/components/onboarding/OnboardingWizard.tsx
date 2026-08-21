import React from 'react';
import { useNavigate } from '@tanstack/react-router';
import { useOnboardingStore } from '@/store/onboardingStore';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { WelcomeStep } from './steps/WelcomeStep';
import { ApiKeyStep } from './steps/ApiKeyStep';
import { SampleEvaluationStep } from './steps/SampleEvaluationStep';
import { SuccessStep } from './steps/SuccessStep';

export function OnboardingWizard() {
  const navigate = useNavigate();
  const {
    currentStep,
    steps,
    setCurrentStep,
    skipOnboarding,
    onboardingCompleted,
  } = useOnboardingStore();

  React.useEffect(() => {
    if (onboardingCompleted) {
      navigate({ to: '/voice-rooms' });
    }
  }, [onboardingCompleted, navigate]);

  const currentStepData = steps[currentStep];
  const progress = ((currentStep + 1) / steps.length) * 100;

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    if (confirm('Are you sure you want to skip the onboarding? You can restart it later from settings.')) {
      skipOnboarding();
      navigate({ to: '/voice-rooms' });
    }
  };

  const renderStep = () => {
    switch (currentStepData.id) {
      case 'welcome':
        return <WelcomeStep onNext={handleNext} />;
      case 'api-key':
        return <ApiKeyStep onNext={handleNext} />;
      case 'sample-evaluation':
        return <SampleEvaluationStep onNext={handleNext} />;
      case 'success':
        return <SuccessStep />;
      default:
        return null;
    }
  };

  const canGoNext = () => {
    // Check if current step requirements are met
    switch (currentStepData.id) {
      case 'api-key':
        return useOnboardingStore.getState().apiKeyConfigured;
      case 'sample-evaluation':
        return useOnboardingStore.getState().sampleEvaluationRun;
      default:
        return true;
    }
  };

  return (
    <div className="min-h-screen bg-muted/30">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-foreground">
              {currentStepData.title}
            </h1>
            <p className="text-muted-foreground mt-2">
              {currentStepData.description}
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleSkip}
            aria-label="Close onboarding"
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Progress */}
        <div className="mb-8">
          <div className="flex justify-between text-sm text-muted-foreground mb-2">
            <span>Step {currentStep + 1} of {steps.length}</span>
            <span>{Math.round(progress)}% Complete</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>

        {/* Step indicators */}
        <div className="flex justify-center mb-8">
          <div className="flex space-x-2">
            {steps.map((step, index) => (
              <button
                key={step.id}
                onClick={() => index <= currentStep && setCurrentStep(index)}
                className={`w-3 h-3 rounded-full transition-all ${
                  index === currentStep
                    ? 'bg-accent-brand w-8'
                    : index < currentStep
                    ? 'bg-accent-brand/60'
                    : 'bg-border'
                } ${index <= currentStep ? 'cursor-pointer' : 'cursor-not-allowed'}`}
                disabled={index > currentStep}
                aria-label={`Go to ${step.title}`}
              />
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="max-w-4xl mx-auto">
          <div className="surface rounded-xl shadow-lg p-8 min-h-[400px]">
            {renderStep()}
          </div>

          {/* Navigation */}
          <div className="flex justify-between mt-8">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={currentStep === 0}
              className="flex items-center space-x-2"
            >
              <ChevronLeft className="h-4 w-4" />
              <span>Previous</span>
            </Button>

            {currentStepData.id !== 'success' && (
              <Button
                onClick={handleNext}
                disabled={!canGoNext()}
                className="flex items-center space-x-2 bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all"
              >
                <span>Next</span>
                <ChevronRight className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}