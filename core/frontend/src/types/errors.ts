// Centralized error types for better type safety

export interface ApiError {
  response?: {
    data?: {
      message?: string;
      error?: string;
      details?: unknown;
    };
    status?: number;
    statusText?: string;
  };
  message?: string;
  code?: string;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  if (typeof error === 'object' && error !== null) {
    const apiError = error as ApiError;

    if (apiError.response?.data?.message) {
      return apiError.response.data.message;
    }

    if (apiError.response?.data?.error) {
      return apiError.response.data.error;
    }

    if (apiError.message) {
      return apiError.message;
    }
  }

  if (typeof error === 'string') {
    return error;
  }

  return 'An unexpected error occurred';
}