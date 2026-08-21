import React from 'react';
import { Button } from '@/components/ui/button';
import { Rocket, Shield, TrendingUp, Users } from 'lucide-react';

interface WelcomeStepProps {
  onNext: () => void;
}

export function WelcomeStep({ onNext }: WelcomeStepProps) {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-20 h-20 gradient-brand rounded-full mb-4">
          <Rocket className="h-10 w-10 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-foreground mb-4">
          Welcome to Sterna
        </h2>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          Your AI-powered quality evaluation platform. Let's get you set up in just a few minutes.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
        <FeatureCard
          icon={<Shield className="h-6 w-6" />}
          title="Sterna"
          description="Prevent AI regressions before they reach production with automated quality checks."
        />
        <FeatureCard
          icon={<TrendingUp className="h-6 w-6" />}
          title="Performance Metrics"
          description="Track and optimize model performance, latency, and costs across evaluations."
        />
        <FeatureCard
          icon={<Users className="h-6 w-6" />}
          title="Team Collaboration"
          description="Work together with role-based access control and project management."
        />
        <FeatureCard
          icon={<Rocket className="h-6 w-6" />}
          title="100+ Models"
          description="Access OpenRouter's extensive model catalog with automatic fallbacks."
        />
      </div>

      <div className="bg-secondary rounded-lg p-6 mt-8">
        <h3 className="font-semibold text-foreground mb-2">
          What we'll cover:
        </h3>
        <ul className="space-y-2 text-muted-foreground">
          <li className="flex items-start">
            <span className="text-accent-brand mr-2">✓</span>
            Connect your OpenRouter API for model access
          </li>
          <li className="flex items-start">
            <span className="text-accent-brand mr-2">✓</span>
            Understand model tiers and capabilities
          </li>
          <li className="flex items-start">
            <span className="text-accent-brand mr-2">✓</span>
            Learn cost optimization strategies
          </li>
          <li className="flex items-start">
            <span className="text-accent-brand mr-2">✓</span>
            Run your first evaluation
          </li>
        </ul>
      </div>

      <div className="text-center pt-4">
        <Button onClick={onNext} size="lg" className="px-8 bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
          Get Started
        </Button>
        <p className="text-sm text-muted-foreground mt-4">
          Takes about 5 minutes to complete
        </p>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex space-x-4">
      <div className="flex-shrink-0">
        <div className="w-12 h-12 bg-secondary rounded-lg flex items-center justify-center text-accent-brand">
          {icon}
        </div>
      </div>
      <div>
        <h4 className="font-semibold text-foreground mb-1">
          {title}
        </h4>
        <p className="text-sm text-muted-foreground">
          {description}
        </p>
      </div>
    </div>
  );
}