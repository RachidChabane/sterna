import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Slider } from '@/components/ui/slider';
import { useOnboardingStore } from '@/store/onboardingStore';
import { useOnboardingTierStore } from '../onboardingTierStore';
import { Calculator, TrendingDown, AlertTriangle, Lightbulb, DollarSign } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface CostEstimationStepProps {
  onNext: () => void;
}

interface CostEstimate {
  budget: number;
  balanced: number;
  quality: number;
}

const COST_PER_1K_TOKENS = {
  budget: 0.0005,    // $0.50 per million tokens
  balanced: 0.005,   // $5 per million tokens
  quality: 0.05,     // $50 per million tokens
};

const AVG_TOKENS_PER_EVAL = 500; // Average tokens per evaluation (input + output)

export function CostEstimationStep({ onNext }: CostEstimationStepProps) {
  const { completeStep } = useOnboardingStore();
  const { selectedModelTier } = useOnboardingTierStore();
  const [dailyEvaluations, setDailyEvaluations] = useState(100);
  const [criteriaPerEval, setCriteriaPerEval] = useState(5);

  const calculateCosts = (): CostEstimate => {
    const monthlyEvals = dailyEvaluations * 30;
    const totalTokens = monthlyEvals * criteriaPerEval * AVG_TOKENS_PER_EVAL;
    const totalTokensInK = totalTokens / 1000;

    return {
      budget: totalTokensInK * COST_PER_1K_TOKENS.budget,
      balanced: totalTokensInK * COST_PER_1K_TOKENS.balanced,
      quality: totalTokensInK * COST_PER_1K_TOKENS.quality,
    };
  };

  const costs = calculateCosts();
  const selectedCost = costs[selectedModelTier || 'balanced'];

  const handleContinue = () => {
    completeStep('cost-estimation');
    onNext();
  };

  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 dark:bg-green-900 rounded-full mb-4">
          <Calculator className="h-8 w-8 text-green-600 dark:text-green-400" />
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Cost Estimation & Optimization
        </h2>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          Understand and optimize your evaluation costs with our calculator
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          <Card className="p-6">
            <h3 className="font-semibold text-foreground mb-4">
              Your Usage Pattern
            </h3>

            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm font-medium text-foreground/80">
                    Daily Evaluations
                  </label>
                  <span className="text-sm font-semibold text-foreground">
                    {dailyEvaluations.toLocaleString()}
                  </span>
                </div>
                <Slider
                  value={[dailyEvaluations]}
                  onValueChange={([value]) => setDailyEvaluations(value)}
                  min={10}
                  max={10000}
                  step={10}
                  className="mb-2"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>10</span>
                  <span>10,000</span>
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-2">
                  <label className="text-sm font-medium text-foreground/80">
                    Criteria per Evaluation
                  </label>
                  <span className="text-sm font-semibold text-foreground">
                    {criteriaPerEval}
                  </span>
                </div>
                <Slider
                  value={[criteriaPerEval]}
                  onValueChange={([value]) => setCriteriaPerEval(value)}
                  min={1}
                  max={20}
                  step={1}
                  className="mb-2"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>1</span>
                  <span>20</span>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-border">
              <div className="text-sm space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Monthly evaluations:</span>
                  <span className="font-medium text-foreground">
                    {(dailyEvaluations * 30).toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Total criteria checks:</span>
                  <span className="font-medium text-foreground">
                    {(dailyEvaluations * 30 * criteriaPerEval).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          </Card>

          <Card className="p-6 gradient-brand">
            <div className="flex items-center space-x-3 mb-3">
              <DollarSign className="h-5 w-5 text-white" />
              <h3 className="font-semibold text-white">
                Your Estimated Monthly Cost
              </h3>
            </div>
            <div className="text-3xl font-bold text-white">
              ${selectedCost.toFixed(2)}
            </div>
            <p className="text-sm text-white/90 mt-2">
              Using {selectedModelTier || 'balanced'} tier models
            </p>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-6">
            <h3 className="font-semibold text-foreground mb-4">
              Cost Comparison by Tier
            </h3>

            <div className="space-y-4">
              <CostTierRow
                tier="Budget"
                cost={costs.budget}
                selected={selectedModelTier === 'budget'}
                savings={costs.quality - costs.budget}
              />
              <CostTierRow
                tier="Balanced"
                cost={costs.balanced}
                selected={selectedModelTier === 'balanced'}
                savings={costs.quality - costs.balanced}
              />
              <CostTierRow
                tier="Quality"
                cost={costs.quality}
                selected={selectedModelTier === 'quality'}
                savings={0}
              />
            </div>
          </Card>

          <Card className="p-6 bg-amber-50 dark:bg-amber-900/20">
            <div className="flex items-center space-x-2 mb-3">
              <Lightbulb className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              <h3 className="font-semibold text-foreground">
                Cost Optimization Tips
              </h3>
            </div>

            <ul className="space-y-3 text-sm">
              <OptimizationTip
                icon={<TrendingDown className="h-4 w-4" />}
                text="Use budget models for development and testing"
              />
              <OptimizationTip
                icon={<TrendingDown className="h-4 w-4" />}
                text="Mix tiers: budget for simple checks, quality for complex"
              />
              <OptimizationTip
                icon={<TrendingDown className="h-4 w-4" />}
                text="Set cost limits per project to prevent overruns"
              />
              <OptimizationTip
                icon={<TrendingDown className="h-4 w-4" />}
                text="Use sampling for large datasets instead of full evaluation"
              />
              <OptimizationTip
                icon={<TrendingDown className="h-4 w-4" />}
                text="Cache results to avoid re-evaluating unchanged data"
              />
            </ul>
          </Card>
        </div>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          <strong>Budget Protection:</strong> Sterna includes cost limits and alerts to prevent
          unexpected charges. You can set maximum spending per project and receive notifications
          when approaching limits.
        </AlertDescription>
      </Alert>

      <div className="text-center pt-4">
        <Button onClick={handleContinue} size="lg" className="bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
          Continue to Sample Evaluation
        </Button>
      </div>
    </div>
  );
}

function CostTierRow({
  tier,
  cost,
  selected,
  savings
}: {
  tier: string;
  cost: number;
  selected: boolean;
  savings: number;
}) {
  return (
    <div className={`flex items-center justify-between p-3 rounded-lg ${
      selected ? 'bg-muted/30 ring-2 ring-accent-brand' : 'bg-secondary'
    }`}>
      <div className="flex items-center space-x-3">
        <div className={`w-3 h-3 rounded-full ${
          tier === 'Budget' ? 'bg-green-500' :
          tier === 'Balanced' ? 'bg-accent-brand' : 'bg-accent-brand'
        }`} />
        <span className="font-medium text-foreground">
          {tier}
        </span>
        {selected && (
          <span className="text-xs bg-accent-brand text-white px-2 py-1 rounded">
            SELECTED
          </span>
        )}
      </div>
      <div className="text-right">
        <div className="font-semibold text-foreground">
          ${cost.toFixed(2)}/mo
        </div>
        {savings > 0 && (
          <div className="text-xs text-green-600 dark:text-green-400">
            Save ${savings.toFixed(2)}
          </div>
        )}
      </div>
    </div>
  );
}

function OptimizationTip({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <li className="flex items-start space-x-2">
      <span className="text-amber-600 dark:text-amber-400 mt-0.5">{icon}</span>
      <span className="text-foreground/80">{text}</span>
    </li>
  );
}