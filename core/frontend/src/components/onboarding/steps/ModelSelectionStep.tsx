import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { useOnboardingStore } from '@/store/onboardingStore';
import { useOnboardingTierStore } from '../onboardingTierStore';
import { DollarSign, Zap, Crown, Check, Info } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface ModelSelectionStepProps {
  onNext: () => void;
}

type ModelTier = 'budget' | 'balanced' | 'quality';

interface TierOption {
  value: ModelTier;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  pros: string[];
  cons: string[];
  monthlyEstimate: string;
}

const tierOptions: TierOption[] = [
  {
    value: 'budget',
    label: 'Budget Tier',
    description: 'Cost-effective for development and simple evaluations',
    icon: <DollarSign className="h-5 w-5" />,
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/20',
    pros: [
      'Lowest cost per evaluation',
      'Fast response times',
      'Great for development',
    ],
    cons: [
      'Limited reasoning capability',
      'May miss nuanced issues',
    ],
    monthlyEstimate: '$10-50',
  },
  {
    value: 'balanced',
    label: 'Balanced Tier',
    description: 'Optimal balance of performance and cost for production',
    icon: <Zap className="h-5 w-5" />,
    color: 'text-accent-brand',
    bgColor: 'gradient-brand',
    pros: [
      'Good reasoning capability',
      'Reliable for CI/CD',
      'Cost-effective at scale',
    ],
    cons: [
      'Moderate cost increase',
      'Slightly slower than budget',
    ],
    monthlyEstimate: '$50-200',
  },
  {
    value: 'quality',
    label: 'Quality Tier',
    description: 'Maximum accuracy for critical evaluations',
    icon: <Crown className="h-5 w-5" />,
    color: 'text-accent-brand',
    bgColor: 'bg-secondary',
    pros: [
      'Best reasoning capability',
      'Catches subtle issues',
      'Expert-level analysis',
    ],
    cons: [
      'Highest cost',
      'Slower processing',
    ],
    monthlyEstimate: '$200-1000+',
  },
];

export function ModelSelectionStep({ onNext }: ModelSelectionStepProps) {
  const { completeStep } = useOnboardingStore();
  const { selectedModelTier, setSelectedModelTier } = useOnboardingTierStore();
  const [selectedTier, setSelectedTier] = useState<ModelTier>(
    selectedModelTier || 'balanced'
  );

  const handleContinue = () => {
    setSelectedModelTier(selectedTier);
    completeStep('model-selection');
    onNext();
  };

  const selectedOption = tierOptions.find(t => t.value === selectedTier);

  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Select Your Default Model Tier
        </h2>
        <p className="text-muted-foreground">
          Choose your preferred tier for evaluations. You can change this anytime or mix tiers per rubric.
        </p>
      </div>

      <RadioGroup
        value={selectedTier}
        onValueChange={(value) => setSelectedTier(value as ModelTier)}
        className="space-y-4"
      >
        {tierOptions.map((tier) => (
          <Card
            key={tier.value}
            className={`relative cursor-pointer transition-all ${
              selectedTier === tier.value
                ? 'ring-2 ring-accent-brand bg-muted/30'
                : 'hover:shadow-md'
            }`}
            onClick={() => setSelectedTier(tier.value)}
          >
            <div className="p-6">
              <div className="flex items-start space-x-4">
                <RadioGroupItem
                  value={tier.value}
                  id={tier.value}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <div className={`p-2 rounded-lg ${tier.bgColor} ${tier.value === 'balanced' ? 'text-white' : tier.color}`}>
                      {tier.icon}
                    </div>
                    <Label
                      htmlFor={tier.value}
                      className="text-lg font-semibold cursor-pointer"
                    >
                      {tier.label}
                    </Label>
                    {tier.value === 'balanced' && (
                      <span className="bg-accent-brand text-white text-xs font-medium px-2 py-1 rounded">
                        RECOMMENDED
                      </span>
                    )}
                  </div>

                  <p className="text-muted-foreground mb-3">
                    {tier.description}
                  </p>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="font-medium text-green-700 dark:text-green-400 mb-1">
                        Pros:
                      </p>
                      <ul className="space-y-1">
                        {tier.pros.map((pro, index) => (
                          <li key={index} className="flex items-start">
                            <Check className="h-3 w-3 text-green-600 dark:text-green-400 mr-1 mt-0.5 flex-shrink-0" />
                            <span className="text-muted-foreground">
                              {pro}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="font-medium text-amber-700 dark:text-amber-400 mb-1">
                        Cons:
                      </p>
                      <ul className="space-y-1">
                        {tier.cons.map((con, index) => (
                          <li key={index} className="flex items-start">
                            <span className="text-amber-600 dark:text-amber-400 mr-1">
                              •
                            </span>
                            <span className="text-muted-foreground">
                              {con}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="mt-3 pt-3 border-t border-border">
                    <p className="text-sm">
                      <span className="text-muted-foreground">
                        Estimated monthly cost:
                      </span>{' '}
                      <span className="font-semibold text-foreground">
                        {tier.monthlyEstimate}
                      </span>
                      <span className="text-muted-foreground ml-1">
                        (based on ~10K evaluations)
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </RadioGroup>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>Flexibility:</strong> You're not locked into one tier. Each rubric can specify
          different models, and you can override selections for specific evaluation runs.
        </AlertDescription>
      </Alert>

      {selectedOption && (
        <div className={`rounded-lg p-4 ${selectedOption.value === 'balanced' ? 'gradient-brand' : selectedOption.bgColor}`}>
          <p className={`text-sm font-medium ${selectedOption.value === 'balanced' ? 'text-white' : 'text-foreground'}`}>
            You selected: <strong>{selectedOption.label}</strong>
          </p>
          <p className={`text-sm mt-1 ${selectedOption.value === 'balanced' ? 'text-white/90' : 'text-muted-foreground'}`}>
            Perfect for {selectedOption.value === 'budget' ? 'getting started and development' :
                        selectedOption.value === 'balanced' ? 'production workloads' :
                        'mission-critical evaluations'}.
          </p>
        </div>
      )}

      <div className="text-center pt-4">
        <Button onClick={handleContinue} size="lg" className="bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
          Continue with {selectedOption?.label}
        </Button>
      </div>
    </div>
  );
}