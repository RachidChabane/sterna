import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useNavigate } from '@tanstack/react-router';
import { useOnboardingStore } from '@/store/onboardingStore';
import { SITE_CONFIG } from '@/config/site';
import {
  Trophy,
  Sparkles,
  ArrowRight,
  FileText,
  BarChart3,
  Settings,
  BookOpen,
  MessageSquare,
  Zap,
  Check,
  PartyPopper,
} from 'lucide-react';
import confetti from 'canvas-confetti';

export function SuccessStep() {
  const navigate = useNavigate();
  const { completeOnboarding } = useOnboardingStore();
  const [showConfetti, setShowConfetti] = useState(false);

  useEffect(() => {
    // Trigger confetti animation
    if (!showConfetti) {
      setShowConfetti(true);
      const duration = 3 * 1000;
      const animationEnd = Date.now() + duration;

      const randomInRange = (min: number, max: number) => {
        return Math.random() * (max - min) + min;
      };

      const interval: any = setInterval(() => {
        const timeLeft = animationEnd - Date.now();

        if (timeLeft <= 0) {
          clearInterval(interval);
          return;
        }

        const particleCount = 50 * (timeLeft / duration);

        confetti({
          particleCount,
          startVelocity: 30,
          spread: 360,
          origin: {
            x: randomInRange(0.1, 0.3),
            y: Math.random() - 0.2,
          },
          colors: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'],
        });

        confetti({
          particleCount,
          startVelocity: 30,
          spread: 360,
          origin: {
            x: randomInRange(0.7, 0.9),
            y: Math.random() - 0.2,
          },
          colors: ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6'],
        });
      }, 250);

      return () => clearInterval(interval);
    }
  }, [showConfetti]);

  const handleGetStarted = () => {
    completeOnboarding();
    navigate({ to: '/chats' });
  };

  const quickActions = [
    {
      icon: <MessageSquare className="h-5 w-5" />,
      title: 'Start Chatting',
      description: 'Talk to any model, compare responses side by side',
      path: '/chats',
    },
    {
      icon: <BarChart3 className="h-5 w-5" />,
      title: 'Compare Models',
      description: 'See pricing and capabilities across 100+ models',
      path: '/models',
    },
    {
      icon: <Zap className="h-5 w-5" />,
      title: 'Connect a Tool',
      description: 'Add an MCP connector to your chats',
      path: '/connectors',
    },
    {
      icon: <FileText className="h-5 w-5" />,
      title: 'Build a Knowledge Base',
      description: 'Upload documents to ground answers in your own data',
      path: '/knowledge',
    },
  ];

  const resources = [
    {
      icon: <BookOpen className="h-4 w-4" />,
      title: 'Documentation',
      description: 'Learn about all features',
      url: SITE_CONFIG.docsUrl,
    },
    {
      icon: <MessageSquare className="h-4 w-4" />,
      title: 'Community',
      description: 'Join our Discord server',
      url: 'https://discord.gg/sterna',
    },
    {
      icon: <Settings className="h-4 w-4" />,
      title: 'API Reference',
      description: 'Integrate with your CI/CD',
      url: '/api/docs',
    },
  ];

  return (
    <div className="space-y-6">
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-yellow-400 to-orange-500 rounded-full mb-4 animate-bounce">
          <Trophy className="h-10 w-10 text-white" />
        </div>

        <h2 className="text-3xl font-bold text-foreground mb-3 flex items-center justify-center gap-2">
          Congratulations! <PartyPopper className="h-8 w-8 text-yellow-500" />
        </h2>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          You're all set up and ready to start evaluating AI quality with confidence.
        </p>

        <div className="flex justify-center items-center space-x-2 mt-4">
          <Sparkles className="h-5 w-5 text-yellow-500 animate-pulse" />
          <span className="text-sm font-medium text-foreground/80">
            Setup completed in less than 5 minutes!
          </span>
          <Sparkles className="h-5 w-5 text-yellow-500 animate-pulse" />
        </div>
      </div>

      <Card className="p-6 gradient-brand">
        <h3 className="font-semibold text-white mb-4">
          What You've Accomplished
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Achievement text="Connected OpenRouter API" />
          <Achievement text="Selected optimal model tier" />
          <Achievement text="Understood cost structure" />
          <Achievement text="Ran your first evaluation" />
        </div>
      </Card>

      <div>
        <h3 className="font-semibold text-foreground mb-4">
          Quick Actions to Get Started
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {quickActions.map((action, index) => (
            <Card
              key={index}
              className="p-4 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => navigate({ to: action.path })}
            >
              <div className="flex items-start space-x-3">
                <div className="w-10 h-10 bg-secondary rounded-lg flex items-center justify-center text-accent-brand flex-shrink-0">
                  {action.icon}
                </div>
                <div className="flex-1">
                  <h4 className="font-medium text-foreground">
                    {action.title}
                  </h4>
                  <p className="text-sm text-muted-foreground mt-1">
                    {action.description}
                  </p>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground mt-1" />
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Card className="p-6 bg-secondary">
        <h3 className="font-semibold text-foreground mb-4">
          Helpful Resources
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {resources.map((resource, index) => (
            <a
              key={index}
              href={resource.url}
              target={resource.url.startsWith('http') ? '_blank' : undefined}
              rel={resource.url.startsWith('http') ? 'noopener noreferrer' : undefined}
              className="flex items-center space-x-2 p-3 rounded-lg hover:bg-background transition-colors"
            >
              <div className="text-muted-foreground">{resource.icon}</div>
              <div>
                <p className="font-medium text-sm text-foreground">
                  {resource.title}
                </p>
                <p className="text-xs text-muted-foreground">
                  {resource.description}
                </p>
              </div>
            </a>
          ))}
        </div>
      </Card>

      <div className="text-center pt-6">
        <Button onClick={handleGetStarted} size="lg" className="px-8 bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
          Get Started
          <ArrowRight className="h-4 w-4 ml-2" />
        </Button>
        <p className="text-sm text-muted-foreground mt-4">
          You can always access these settings later from your account
        </p>
      </div>
    </div>
  );
}

function Achievement({ text }: { text: string }) {
  return (
    <div className="flex items-center space-x-2">
      <div className="w-6 h-6 bg-green-100 dark:bg-green-900 rounded-full flex items-center justify-center flex-shrink-0">
        <Check className="h-3 w-3 text-green-600 dark:text-green-400" />
      </div>
      <span className="text-sm text-white">{text}</span>
    </div>
  );
}