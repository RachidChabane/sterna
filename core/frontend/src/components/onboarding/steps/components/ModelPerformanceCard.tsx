import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Clock, DollarSign, CheckCircle } from 'lucide-react';

export interface EvaluationResult {
  modelId: string;
  modelName: string;
  score: number;
  passed: boolean;
  latency: number;
  cost: number;
  explanation: string;
}

interface ModelPerformanceCardProps {
  modelName: string;
  results: EvaluationResult[];
}

export const ModelPerformanceCard: React.FC<ModelPerformanceCardProps> = ({
  modelName,
  results,
}) => {
  const avgScore = results.reduce((sum, r) => sum + r.score, 0) / results.length;
  const avgLatency = results.reduce((sum, r) => sum + r.latency, 0) / results.length;
  const totalCost = results.reduce((sum, r) => sum + r.cost, 0);
  const passedCount = results.filter(r => r.passed).length;

  return (
    <div className="p-4 rounded-lg bg-muted/30">
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium">{modelName}</span>
        <Badge variant={avgScore > 80 ? 'default' : 'secondary'}>
          {avgScore.toFixed(0)}% accuracy
        </Badge>
      </div>
      <div className="grid grid-cols-3 gap-3 text-sm">
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3 text-muted-foreground" />
          <span>{(avgLatency / 1000).toFixed(1)}s</span>
        </div>
        <div className="flex items-center gap-1">
          <DollarSign className="w-3 h-3 text-muted-foreground" />
          <span>${totalCost.toFixed(2)}</span>
        </div>
        <div className="flex items-center gap-1">
          <CheckCircle className="w-3 h-3 text-muted-foreground" />
          <span>
            {passedCount}/{results.length}
          </span>
        </div>
      </div>
    </div>
  );
};