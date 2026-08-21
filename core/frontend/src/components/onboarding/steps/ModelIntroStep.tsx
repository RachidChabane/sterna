import React from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Zap, Cpu, Crown, TrendingUp, DollarSign, Clock, Sparkles } from 'lucide-react';
import { useOnboardingStore } from '@/store/onboardingStore';
import { pricingUtils } from '@/lib/pricing-utils';

interface ModelIntroStepProps {
  onNext: () => void;
}

export function ModelIntroStep({ onNext }: ModelIntroStepProps) {
  const { completeStep } = useOnboardingStore();

  const handleContinue = () => {
    completeStep('model-intro');
    onNext();
  };

  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center w-16 h-16 gradient-brand rounded-full mb-4">
          <Cpu className="h-8 w-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Understanding Model Tiers
        </h2>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          Choose the right balance of speed, quality, and cost for your evaluations
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ModelTierCard
          tier="Budget"
          icon={<DollarSign className="h-6 w-6" />}
          color="green"
          models={['Llama 3', 'Mistral 7B', 'Gemma']}
          specs={{
            cost: `$0.1-1/${pricingUtils.getUnitLabel()} tokens`,
            speed: '100-200 tokens/sec',
            quality: 'Good for simple tasks',
          }}
          useCases={[
            'Binary classification',
            'Simple text matching',
            'Basic validation',
          ]}
        />

        <ModelTierCard
          tier="Balanced"
          icon={<Zap className="h-6 w-6" />}
          color="blue"
          models={['Claude 3 Haiku', 'GPT-3.5 Turbo', 'Gemini Pro']}
          specs={{
            cost: `$1-10/${pricingUtils.getUnitLabel()} tokens`,
            speed: '50-100 tokens/sec',
            quality: 'Great for most evaluations',
          }}
          useCases={[
            'Complex reasoning',
            'Multi-criteria evaluation',
            'Content analysis',
          ]}
          recommended
        />

        <ModelTierCard
          tier="Quality"
          icon={<Crown className="h-6 w-6" />}
          color="purple"
          models={['GPT-4', 'Claude 3 Opus', 'Gemini Ultra']}
          specs={{
            cost: `$10-100/${pricingUtils.getUnitLabel()} tokens`,
            speed: '20-50 tokens/sec',
            quality: 'Best for critical tasks',
          }}
          useCases={[
            'Expert-level analysis',
            'Nuanced understanding',
            'Mission-critical evals',
          ]}
        />
      </div>

      <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-6">
        <h3 className="font-semibold text-foreground mb-3 flex items-center">
          <TrendingUp className="h-5 w-5 mr-2 text-amber-600 dark:text-amber-400" />
          Smart Model Selection Tips
        </h3>
        <ul className="space-y-2 text-sm text-foreground/80">
          <li className="flex items-start">
            <span className="text-amber-600 dark:text-amber-400 mr-2">→</span>
            <span>
              <strong>Start with Budget</strong> for initial testing and development
            </span>
          </li>
          <li className="flex items-start">
            <span className="text-amber-600 dark:text-amber-400 mr-2">→</span>
            <span>
              <strong>Use Balanced</strong> for production evaluations and CI/CD
            </span>
          </li>
          <li className="flex items-start">
            <span className="text-amber-600 dark:text-amber-400 mr-2">→</span>
            <span>
              <strong>Reserve Quality</strong> for final validation and critical decisions
            </span>
          </li>
          <li className="flex items-start">
            <span className="text-amber-600 dark:text-amber-400 mr-2">→</span>
            <span>
              <strong>Mix and match</strong> different tiers for different criteria in the same rubric
            </span>
          </li>
        </ul>
      </div>

      <div className="bg-secondary rounded-lg p-4">
        <div className="flex items-center space-x-3">
          <Clock className="h-5 w-5 text-accent-brand flex-shrink-0" />
          <p className="text-sm text-foreground/80">
            <strong>Pro tip:</strong> Sterna automatically handles fallbacks between models in the same tier,
            ensuring your evaluations always complete even if a specific model is unavailable.
          </p>
        </div>
      </div>

      <div className="text-center pt-4">
        <Button onClick={handleContinue} size="lg" className="bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
          Continue to Model Selection
        </Button>
      </div>
    </div>
  );
}

interface ModelTierCardProps {
  tier: string;
  icon: React.ReactNode;
  color: 'green' | 'blue' | 'purple';
  models: string[];
  specs: {
    cost: string;
    speed: string;
    quality: string;
  };
  useCases: string[];
  recommended?: boolean;
}

function ModelTierCard({
  tier,
  icon,
  color,
  models,
  specs,
  useCases,
  recommended,
}: ModelTierCardProps) {
  const colorClasses = {
    green: 'bg-green-100 dark:bg-green-900/20 text-green-600 dark:text-green-400 border-green-200 dark:border-green-800',
    blue: 'gradient-brand text-white border-none',
    purple: 'bg-secondary text-accent-brand border-accent-brand/20',
  };

  return (
    <Card className={`relative p-6 ${recommended ? 'ring-2 ring-accent-brand' : ''}`}>
      {recommended && (
        <div className="absolute -top-3 left-1/2 transform -translate-x-1/2">
          <span className="bg-accent-brand text-white text-xs font-semibold px-3 py-1 rounded-full">
            RECOMMENDED
          </span>
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-foreground">
          {tier}
        </h3>
        <div className={`p-2 rounded-lg ${colorClasses[color]}`}>
          {icon}
        </div>
      </div>

      <div className="space-y-3 mb-4">
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">
            MODELS
          </p>
          <p className="text-sm text-foreground/80">
            {models.join(', ')}
          </p>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">
            SPECS
          </p>
          <ul className="text-xs space-y-1">
            <li className="text-muted-foreground flex items-center gap-1">
              <DollarSign className="h-3 w-3" /> {specs.cost}
            </li>
            <li className="text-muted-foreground flex items-center gap-1">
              <Zap className="h-3 w-3" /> {specs.speed}
            </li>
            <li className="text-muted-foreground flex items-center gap-1">
              <Sparkles className="h-3 w-3" /> {specs.quality}
            </li>
          </ul>
        </div>

        <div>
          <p className="text-xs font-medium text-muted-foreground mb-1">
            BEST FOR
          </p>
          <ul className="text-xs space-y-1">
            {useCases.map((useCase, index) => (
              <li key={index} className="text-muted-foreground">
                • {useCase}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}