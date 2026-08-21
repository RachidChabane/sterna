import React from 'react';
import { Card } from '@/components/ui/card';
import { CheckCircle } from 'lucide-react';
import type { EvaluationResult } from './ModelPerformanceCard';

interface EvaluationSummaryProps {
  results: EvaluationResult[];
  totalCost: number;
  totalTime: number;
}

export const EvaluationSummary: React.FC<EvaluationSummaryProps> = ({
  results,
  totalCost,
  totalTime,
}) => {
  const passRate = results.length > 0
    ? (results.filter(r => r.passed).length / results.length) * 100
    : 0;

  return (
    <Card className="p-6">
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <CheckCircle className="w-5 h-5 text-green-500" />
        Evaluation Complete
      </h3>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Total Cost</p>
          <p className="text-xl font-bold">${totalCost.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Total Time</p>
          <p className="text-xl font-bold">{(totalTime / 1000).toFixed(1)}s</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Pass Rate</p>
          <p className="text-xl font-bold">{passRate.toFixed(0)}%</p>
        </div>
      </div>
    </Card>
  );
};