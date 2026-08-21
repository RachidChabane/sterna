import React from 'react';
import { Card } from '@/components/ui/card';
import { Sparkles, FileText, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SampleTypeSelectorProps {
  selectedSample: string;
  onSelectSample: (sample: string) => void;
  sampleCounts: Record<string, number>;
  disabled?: boolean;
}

const SAMPLE_TYPES = {
  sentiment: { icon: <Sparkles />, label: 'Sentiment Analysis' },
  summarization: { icon: <FileText />, label: 'Summarization' },
  reasoning: { icon: <TrendingUp />, label: 'Reasoning' },
};

export const SampleTypeSelector: React.FC<SampleTypeSelectorProps> = ({
  selectedSample,
  onSelectSample,
  sampleCounts,
  disabled = false,
}) => {
  return (
    <Card className="p-6">
      <h3 className="font-semibold mb-4">Choose Evaluation Type</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {Object.entries(SAMPLE_TYPES).map(([key, { icon, label }]) => (
          <Card
            key={key}
            className={cn(
              'p-4 transition-colors',
              disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
              selectedSample === key
                ? 'border-primary bg-primary/5'
                : 'hover:border-muted-foreground/50'
            )}
            onClick={() => !disabled && onSelectSample(key)}
          >
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-primary/10 rounded text-primary">
                {React.cloneElement(icon, { className: 'w-5 h-5' })}
              </div>
              <div>
                <p className="font-medium">{label}</p>
                <p className="text-xs text-muted-foreground">
                  {sampleCounts[key]} samples
                </p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </Card>
  );
};