// Centralized UI text constants for better maintainability and i18n support

export const TEXT = {
  // Application
  APP_NAME: 'Sterna',

  // Onboarding Wizard
  ONBOARDING: {
    WELCOME: {
      TITLE: 'Welcome to Sterna',
      DESCRIPTION: 'Introduction to AI evaluation with OpenRouter',
    },
    API_KEY: {
      TITLE: 'Setup OpenRouter API Key',
      DESCRIPTION: 'Configure your OpenRouter API key for model access',
      VALIDATE_SUCCESS: 'API Key Validated Successfully',
      VALIDATE_ERROR: 'Invalid API Key',
      PLACEHOLDER: 'Enter your OpenRouter API key',
      HELPER_TEXT: 'Your API key is securely stored server-side',
    },
    MODEL_SELECTION: {
      TITLE: 'Choose Your Models',
      DESCRIPTION: 'Select models for your evaluation needs',
      NO_MODELS: 'No models selected',
      SELECT_PROMPT: 'Select at least one model to continue',
    },
    COST_ESTIMATION: {
      TITLE: 'Understand Costs',
      DESCRIPTION: 'Learn about token usage and cost optimization',
      ESTIMATED_LABEL: 'Estimated Tokens',
      COST_PER_RUN: 'Cost per evaluation run',
    },
    SAMPLE_EVALUATION: {
      TITLE: 'Try a Sample Evaluation',
      DESCRIPTION: 'Run your first evaluation with multiple models',
      RUN_BUTTON: 'Run Sample Evaluation',
      RUNNING: 'Running Evaluation...',
      COMPLETE_TITLE: 'Evaluation Complete!',
      COMPLETE_MESSAGE: 'Successfully evaluated samples with selected models',
      FAILED_TITLE: 'Evaluation Failed',
      FAILED_MESSAGE: 'An error occurred during evaluation. Please try again.',
      TRY_AGAIN: 'Try Another Evaluation',
    },
    SUCCESS: {
      TITLE: 'Setup Complete!',
      DESCRIPTION: "You're ready to start evaluating",
      CTA: 'Start Evaluating',
    },
  },

  // Model Names
  MODELS: {
    'gpt-3.5-turbo': 'GPT-3.5 Turbo',
    'gpt-4': 'GPT-4',
    'gpt-4-turbo': 'GPT-4 Turbo',
    'claude-3-haiku': 'Claude 3 Haiku',
    'claude-3-sonnet': 'Claude 3 Sonnet',
    'claude-3-opus': 'Claude 3 Opus',
    'gemini-pro': 'Gemini Pro',
    'gemini-ultra': 'Gemini Ultra',
    'llama-2-70b': 'Llama 2 70B',
    'mixtral-8x7b': 'Mixtral 8x7B',
  },

  // Sample Types
  SAMPLE_TYPES: {
    SENTIMENT: 'Sentiment Analysis',
    SUMMARIZATION: 'Summarization',
    REASONING: 'Reasoning',
    CODE_GENERATION: 'Code Generation',
    TRANSLATION: 'Translation',
  },

  // Common Actions
  ACTIONS: {
    NEXT: 'Next',
    PREVIOUS: 'Previous',
    CONTINUE: 'Continue',
    CANCEL: 'Cancel',
    SAVE: 'Save',
    DELETE: 'Delete',
    EDIT: 'Edit',
    CLOSE: 'Close',
    SUBMIT: 'Submit',
    RESET: 'Reset',
    RETRY: 'Retry',
  },

  // Status Messages
  STATUS: {
    LOADING: 'Loading...',
    PROCESSING: 'Processing...',
    SAVING: 'Saving...',
    SUCCESS: 'Success',
    ERROR: 'Error',
    WARNING: 'Warning',
    INFO: 'Information',
  },

  // Metrics
  METRICS: {
    TOTAL_COST: 'Total Cost',
    TOTAL_TIME: 'Total Time',
    PASS_RATE: 'Pass Rate',
    ACCURACY: 'accuracy',
    LATENCY: 'Latency',
    TOKENS_USED: 'Tokens Used',
  },

  // Error Messages
  ERRORS: {
    GENERIC: 'An unexpected error occurred. Please try again.',
    NETWORK: 'Network error. Please check your connection.',
    VALIDATION: 'Please check your input and try again.',
    NOT_FOUND: 'Resource not found.',
    UNAUTHORIZED: 'You are not authorized to perform this action.',
    SESSION_EXPIRED: 'Your session has expired. Please log in again.',
  },

  // Tooltips
  TOOLTIPS: {
    API_KEY_INFO: 'Your API key is used to authenticate with OpenRouter',
    MODEL_SELECTION_INFO: 'Choose models based on your accuracy and cost requirements',
    TOKEN_ESTIMATION_INFO: 'Estimate based on typical evaluation dataset size',
  },
} as const;

// Helper function to get model name with fallback
export const getModelDisplayName = (modelId: string): string => {
  return TEXT.MODELS[modelId as keyof typeof TEXT.MODELS] || modelId;
};