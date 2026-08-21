import React from 'react';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Eye } from 'lucide-react';

export interface SampleData {
  id: string;
  input: string;
  expected: string;
  category: string;
}

interface SamplePreviewProps {
  samples: SampleData[];
}

export const SamplePreview: React.FC<SamplePreviewProps> = ({ samples }) => {
  return (
    <Card className="p-6">
      <h3 className="font-semibold mb-4 flex items-center gap-2">
        <Eye className="w-5 h-5" />
        Sample Preview
      </h3>
      <ScrollArea className="h-[200px]">
        <div className="space-y-3">
          {samples.map((sample) => (
            <div key={sample.id} className="p-3 rounded-lg bg-muted/30">
              <Badge variant="outline" className="mb-2">
                {sample.category}
              </Badge>
              <p className="text-sm mb-2">
                <span className="font-medium">Input:</span> {sample.input}
              </p>
              <p className="text-sm text-muted-foreground">
                <span className="font-medium">Expected:</span> {sample.expected}
              </p>
            </div>
          ))}
        </div>
      </ScrollArea>
    </Card>
  );
};