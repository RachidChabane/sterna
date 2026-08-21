import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useOnboardingStore } from '@/store/onboardingStore';
import { Key, ExternalLink, Eye, EyeOff, Check, AlertCircle } from 'lucide-react';
import { api } from '@/api/client';
import { toast } from '@/hooks/use-toast';

interface ApiKeyStepProps {
  onNext: () => void;
}

export function ApiKeyStep({ onNext }: ApiKeyStepProps) {
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [validated, setValidated] = useState(false);
  const { setApiKeyConfigured, completeStep } = useOnboardingStore();

  const handleTestConnection = async () => {
    if (!apiKey.trim()) {
      toast({
        title: 'API Key Required',
        description: 'Please enter your OpenRouter API key',
        variant: 'destructive',
      });
      return;
    }

    setTesting(true);
    try {
      // Test the API key by fetching available models
      const response = await api.post('/llm/models/test-connection/', {
        api_key: apiKey,
      });

      if (response.data.success) {
        setValidated(true);
        setApiKeyConfigured(true);
        completeStep('api-key');

        // Save the API key to settings
        await api.post('/settings/openrouter/', {
          api_key: apiKey,
        });

        toast({
          title: 'Success!',
          description: 'Your OpenRouter API key is valid and has been saved.',
        });
      }
    } catch (error) {
      toast({
        title: 'Connection Failed',
        description: 'Unable to validate the API key. Please check and try again.',
        variant: 'destructive',
      });
      setValidated(false);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-4 mb-6">
        <div className="w-12 h-12 gradient-brand rounded-full flex items-center justify-center">
          <Key className="h-6 w-6 text-white" />
        </div>
        <div>
          <h2 className="text-xl font-semibold text-foreground">
            Configure OpenRouter API
          </h2>
          <p className="text-muted-foreground">
            Connect to 100+ AI models with a single API
          </p>
        </div>
      </div>

      <div className="bg-secondary rounded-lg p-6">
        <h3 className="font-semibold text-foreground mb-3">
          What is OpenRouter?
        </h3>
        <p className="text-muted-foreground mb-4">
          OpenRouter provides unified access to models from OpenAI, Anthropic, Google, Meta, and more.
          With automatic fallbacks and competitive pricing, it's the ideal solution for production AI applications.
        </p>
        <div className="flex flex-wrap gap-3">
          <FeatureBadge text="100+ Models" />
          <FeatureBadge text="Automatic Fallbacks" />
          <FeatureBadge text="Usage-Based Pricing" />
          <FeatureBadge text="Single API" />
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <h3 className="font-semibold text-foreground mb-3">
            Get Your API Key
          </h3>
          <ol className="space-y-3 text-sm">
            <Step number="1" text="Visit OpenRouter.ai and create an account" />
            <Step number="2" text="Navigate to Settings → API Keys" />
            <Step number="3" text="Create a new API key and copy it" />
            <Step number="4" text="Paste it below to continue" />
          </ol>
          <div className="mt-3">
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-accent-brand hover:text-accent-brand/80 hover:underline"
            >
              <span>Get your API key from OpenRouter</span>
              <ExternalLink className="h-4 w-4 ml-1" />
            </a>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="api-key">OpenRouter API Key</Label>
          <div className="relative">
            <Input
              id="api-key"
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-or-v1-..."
              className="pr-24"
            />
            <div className="absolute right-1 top-1 flex space-x-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowKey(!showKey)}
                className="h-7 w-7 p-0"
              >
                {showKey ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </Button>
              {validated && (
                <div className="flex items-center px-2">
                  <Check className="h-4 w-4 text-green-600" />
                </div>
              )}
            </div>
          </div>
          {apiKey && !apiKey.startsWith('sk-or-') && (
            <p className="text-sm text-amber-600 dark:text-amber-400">
              OpenRouter API keys typically start with "sk-or-"
            </p>
          )}
        </div>

        <div className="flex space-x-3">
          <Button
            onClick={handleTestConnection}
            disabled={testing || !apiKey.trim()}
            variant={validated ? 'outline' : 'default'}
          >
            {testing ? 'Testing...' : validated ? 'Test Again' : 'Test Connection'}
          </Button>
          {validated && (
            <Button onClick={onNext} className="bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all">
              Continue
            </Button>
          )}
        </div>
      </div>

      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          <strong>Security Note:</strong> Your API key is encrypted and stored securely.
          It will never be exposed in the frontend or logged.
        </AlertDescription>
      </Alert>
    </div>
  );
}

function FeatureBadge({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-background text-foreground border border-border">
      {text}
    </span>
  );
}

function Step({ number, text }: { number: string; text: string }) {
  return (
    <li className="flex items-start">
      <span className="flex-shrink-0 w-6 h-6 bg-secondary rounded-full flex items-center justify-center text-xs font-semibold text-accent-brand mr-3">
        {number}
      </span>
      <span className="text-muted-foreground">{text}</span>
    </li>
  );
}