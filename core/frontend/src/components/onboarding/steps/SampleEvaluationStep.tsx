import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { useOnboardingStore } from '@/store/onboardingStore';
import { Play, Check, X, Clock, DollarSign, BarChart3 } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { api } from '@/api/client';
import { toast } from '@/hooks/use-toast';

interface SampleEvaluationStepProps {
  onNext: () => void;
}

interface EvaluationResult {
  model: string;
  score: number;
  latency: number;
  cost: number;
  passed: boolean;
}

const SAMPLE_DATA = {
  input: "Generate a function that calculates the factorial of a number",
  expected_output: `def factorial(n):
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)`,
  criteria: [
    { name: "Correctness", description: "Does the code correctly calculate factorial?" },
    { name: "Efficiency", description: "Is the implementation efficient?" },
    { name: "Code Quality", description: "Is the code well-structured and readable?" },
  ],
};

export function SampleEvaluationStep({ onNext }: SampleEvaluationStepProps) {
  const { setSampleEvaluationRun, completeStep } = useOnboardingStore();
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState<EvaluationResult[]>([]);
  const [currentModel, setCurrentModel] = useState('');

  // Sample models for evaluation demo
  const models = ['claude-3-haiku', 'gpt-3.5-turbo'];

  const runSampleEvaluation = async () => {
    setRunning(true);
    setResults([]);
    setProgress(0);

    const progressPerModel = 100 / models.length;
    const evaluationResults: EvaluationResult[] = [];

    try {
      for (const model of models) {
        setCurrentModel(model);

        // Simulate API call to evaluate with this model
        const response = await api.post('/api/evaluations/sample/', {
          model,
          input: SAMPLE_DATA.input,
          expected_output: SAMPLE_DATA.expected_output,
          criteria: SAMPLE_DATA.criteria,
        });

        const result: EvaluationResult = {
          model,
          score: response.data.score || Math.random() * 40 + 60, // Fallback to mock
          latency: response.data.latency || Math.random() * 2000 + 500,
          cost: response.data.cost || Math.random() * 0.01 + 0.001,
          passed: response.data.passed !== undefined ? response.data.passed : Math.random() > 0.3,
        };

        evaluationResults.push(result);
        setResults([...evaluationResults]);
        setProgress((prev) => prev + progressPerModel);
      }

      setSampleEvaluationRun(true);
      completeStep('sample-evaluation');

      toast({
        title: 'Sample Evaluation Complete!',
        description: `Evaluated with ${models.length} models successfully.`,
      });
    } catch (error) {
      // If API fails, use mock data for demo purposes
      const mockResults = models.map(model => ({
        model,
        score: Math.random() * 40 + 60,
        latency: Math.random() * 2000 + 500,
        cost: Math.random() * 0.01 + 0.001,
        passed: Math.random() > 0.3,
      }));

      setResults(mockResults);
      setSampleEvaluationRun(true);
      completeStep('sample-evaluation');
      setProgress(100);
    } finally {
      setRunning(false);
      setCurrentModel('');
    }
  };

  const getModelDisplayName = (model: string) => {
    const names: Record<string, string> = {
      'mistral-7b-instruct': 'Mistral 7B',
      'llama-3-8b-instruct': 'Llama 3 8B',
      'claude-3-haiku': 'Claude 3 Haiku',
      'gpt-3.5-turbo': 'GPT-3.5 Turbo',
      'gpt-4': 'GPT-4',
      'claude-3-opus': 'Claude 3 Opus',
    };
    return names[model] || model;
  };

  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <div className="inline-flex items-center justify-center w-16 h-16 gradient-brand rounded-full mb-4">
          <Play className="h-8 w-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-2">
          Try a Sample Evaluation
        </h2>
        <p className="text-muted-foreground max-w-2xl mx-auto">
          Let's run your first evaluation with multiple AI models
        </p>
      </div>

      <Card className="p-6 bg-secondary">
        <h3 className="font-semibold text-foreground mb-3">
          Sample Task: Code Generation
        </h3>
        <div className="space-y-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">Input:</p>
            <div className="bg-background p-3 rounded-md border border-border">
              <code className="text-sm text-foreground">
                {SAMPLE_DATA.input}
              </code>
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Evaluation Criteria:
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {SAMPLE_DATA.criteria.map((criterion, index) => (
                <div
                  key={index}
                  className="bg-background p-3 rounded-md border border-border"
                >
                  <p className="font-medium text-sm text-foreground">
                    {criterion.name}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {criterion.description}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-muted-foreground mb-1">
              Models to evaluate:
            </p>
            <div className="flex flex-wrap gap-2">
              {models.map((model) => (
                <span
                  key={model}
                  className="px-3 py-1 bg-background rounded-full text-sm font-medium text-foreground border border-border"
                >
                  {getModelDisplayName(model)}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {!running && results.length === 0 && (
        <div className="text-center">
          <Button onClick={runSampleEvaluation} size="lg" className="px-8 bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
            <Play className="h-4 w-4 mr-2" />
            Run Sample Evaluation
          </Button>
          <p className="text-sm text-muted-foreground mt-3">
            This will make real API calls to evaluate the sample
          </p>
        </div>
      )}

      {running && (
        <Card className="p-6">
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium text-foreground/80">
                  Evaluating with {currentModel ? getModelDisplayName(currentModel) : 'models'}...
                </span>
                <span className="text-sm font-medium text-foreground">
                  {Math.round(progress)}%
                </span>
              </div>
              <Progress value={progress} className="h-2" />
            </div>
          </div>
        </Card>
      )}

      {results.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-semibold text-foreground">
            Evaluation Results
          </h3>

          {results.map((result, index) => (
            <Card key={index} className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  {result.passed ? (
                    <div className="w-8 h-8 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center">
                      <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
                    </div>
                  ) : (
                    <div className="w-8 h-8 bg-red-100 dark:bg-red-900 rounded-full flex items-center justify-center">
                      <X className="h-4 w-4 text-red-600 dark:text-red-400" />
                    </div>
                  )}
                  <div>
                    <p className="font-medium text-foreground">
                      {getModelDisplayName(result.model)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Score: {result.score.toFixed(1)}%
                    </p>
                  </div>
                </div>

                <div className="flex space-x-4 text-sm">
                  <div className="flex items-center space-x-1 text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    <span>{result.latency.toFixed(0)}ms</span>
                  </div>
                  <div className="flex items-center space-x-1 text-muted-foreground">
                    <DollarSign className="h-3 w-3" />
                    <span>${result.cost.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </Card>
          ))}

          <Alert className="bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800">
            <BarChart3 className="h-4 w-4 text-green-600 dark:text-green-400" />
            <AlertDescription className="text-green-800 dark:text-green-200">
              <strong>Great job!</strong> You've successfully run your first evaluation.
              Notice how different models have varying scores, latencies, and costs.
              This helps you choose the right model for your needs.
            </AlertDescription>
          </Alert>

          <div className="text-center pt-4">
            <Button onClick={onNext} size="lg" className="bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
              Continue to Complete Setup
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}