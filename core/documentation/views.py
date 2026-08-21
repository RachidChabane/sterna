"""
Views for API documentation guides and examples.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.types import OpenApiTypes


class AuthenticationGuideView(APIView):
    """
    Complete guide to JWT authentication in Sterna.
    """

    permission_classes = []
    authentication_classes = []

    @extend_schema(
        responses={200: OpenApiTypes.OBJECT},
        examples=[
            OpenApiExample(
                "Login step",
                description="Excerpt of the JWT flow returned by this endpoint.",
                value={
                    "jwt_flow": {
                        "2_login": {
                            "endpoint": "POST /api/auth/login/",
                            "response": {
                                "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                            },
                        }
                    }
                },
                response_only=True,
            )
        ]
    )
    def get(self, request):
        """Get comprehensive authentication guide."""
        guide = {
            "jwt_flow": {
                "1_register": {
                    "endpoint": "POST /api/auth/register/",
                    "request": {
                        "email": "user@example.com",
                        "password": "SecurePass123!",
                        "first_name": "John",
                        "last_name": "Doe",
                    },
                    "response": {
                        "user": {"id": "uuid", "email": "user@example.com"},
                        "message": "Please verify your email",
                    },
                },
                "2_login": {
                    "endpoint": "POST /api/auth/login/",
                    "request": {
                        "email": "user@example.com",
                        "password": "SecurePass123!",
                    },
                    "response": {
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                        "user": {"id": "uuid", "email": "user@example.com"},
                    },
                },
                "3_use_token": {
                    "description": "Include access token in Authorization header",
                    "headers": {
                        "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGc...",
                        "X-Project-ID": "project-uuid",
                    },
                },
                "4_refresh": {
                    "endpoint": "POST /api/auth/refresh/",
                    "request": {"refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."},
                    "response": {"access": "eyJ0eXAiOiJKV1QiLCJhbGc..."},
                },
                "5_logout": {
                    "endpoint": "POST /api/auth/logout/",
                    "request": {"refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."},
                    "response": {"message": "Successfully logged out"},
                },
            },
            "token_details": {
                "access_token": {
                    "lifetime": "15 minutes",
                    "usage": "Include in Authorization header for API requests",
                    "claims": ["user_id", "email", "exp", "iat"],
                },
                "refresh_token": {
                    "lifetime": "7 days",
                    "usage": "Obtain new access tokens",
                    "storage": "Store securely on client",
                },
            },
            "password_reset": {
                "1_request_reset": {
                    "endpoint": "POST /api/auth/password-reset/",
                    "request": {"email": "user@example.com"},
                    "response": {"message": "Password reset email sent"},
                },
                "2_confirm_reset": {
                    "endpoint": "POST /api/auth/password-reset/confirm/",
                    "request": {
                        "token": "reset-token-from-email",
                        "new_password": "NewSecurePass123!",
                    },
                    "response": {"message": "Password reset successful"},
                },
            },
            "best_practices": [
                "Store tokens securely (httpOnly cookies or secure storage)",
                "Refresh access tokens before expiry",
                "Implement logout by blacklisting tokens",
                "Use HTTPS in production",
                "Handle 401 responses by refreshing tokens",
                "Implement token rotation for enhanced security",
                "Clear tokens on logout across all devices",
            ],
            "error_handling": {
                "401": "Token expired or invalid - refresh token",
                "403": "Insufficient permissions - check user role",
                "422": "Validation error - check request format",
            },
        }
        return Response(guide)


class OpenRouterGuideView(APIView):
    """
    Guide to OpenRouter integration and LLM model usage.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        """Get comprehensive OpenRouter integration guide."""
        guide = {
            "overview": "OpenRouter provides unified access to 100+ LLM models with automatic fallbacks and cost optimization",
            "configuration": {
                "api_key": "Set OPENROUTER_API_KEY environment variable",
                "base_url": "https://openrouter.ai/api/v1",
                "timeout": "30 seconds per request",
                "retry": "3 attempts with exponential backoff",
            },
            "model_tiers": {
                "FAST": {
                    "description": "Low-cost, high-speed models for simple evaluations",
                    "models": ["gpt-3.5-turbo", "claude-instant", "mistral-7b"],
                    "cost_range": "$0.0001-$0.001 per 1K tokens",
                    "use_cases": [
                        "Binary classification",
                        "Simple scoring",
                        "Format validation",
                    ],
                },
                "BALANCED": {
                    "description": "Good performance-to-cost ratio for most evaluations",
                    "models": ["gpt-4", "claude-2", "gemini-pro"],
                    "cost_range": "$0.01-$0.03 per 1K tokens",
                    "use_cases": [
                        "Complex reasoning",
                        "Multi-criteria evaluation",
                        "Code review",
                    ],
                },
                "QUALITY": {
                    "description": "Premium models for complex reasoning tasks",
                    "models": ["gpt-4-turbo", "claude-3-opus", "gemini-ultra"],
                    "cost_range": "$0.03-$0.15 per 1K tokens",
                    "use_cases": [
                        "Expert evaluation",
                        "Creative tasks",
                        "Complex analysis",
                    ],
                },
            },
            "endpoints": {
                "model_catalog": {
                    "endpoint": "GET /api/llm/models/",
                    "description": "Fetch available models with pricing",
                    "response": {
                        "models": [
                            {
                                "id": "gpt-4",
                                "name": "GPT-4",
                                "provider": "openai",
                                "tier": "BALANCED",
                                "pricing": {"prompt": 0.03, "completion": 0.06},
                                "context_length": 8192,
                            }
                        ]
                    },
                },
                "completion": {
                    "endpoint": "POST /api/llm/completion/",
                    "description": "Generate completion with model selection",
                    "request": {
                        "model": "gpt-4",
                        "messages": [
                            {"role": "system", "content": "You are an evaluator"},
                            {"role": "user", "content": "Evaluate this text"},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000,
                    },
                    "response": {
                        "completion": "Generated text...",
                        "usage": {
                            "prompt_tokens": 50,
                            "completion_tokens": 100,
                            "total_cost": 0.009,
                        },
                        "model_used": "gpt-4",
                    },
                },
                "cost_estimate": {
                    "endpoint": "POST /api/llm/estimate-cost/",
                    "description": "Estimate cost before running evaluation",
                    "request": {
                        "model_tier": "BALANCED",
                        "num_samples": 1000,
                        "avg_tokens_per_sample": 500,
                    },
                    "response": {
                        "estimated_cost": 15.00,
                        "breakdown": {
                            "prompt_tokens": 500000,
                            "completion_tokens": 100000,
                            "model": "gpt-4",
                        },
                    },
                },
            },
            "fallback_strategy": {
                "description": "Automatic fallback when models are unavailable",
                "chain": [
                    "1. Try primary model",
                    "2. On rate limit: wait and retry",
                    "3. On error: try next model in tier",
                    "4. On tier exhaustion: try lower tier",
                    "5. Record fallback in metrics",
                ],
                "configuration": {
                    "max_retries": 3,
                    "backoff_factor": 2,
                    "fallback_on": ["rate_limit", "timeout", "server_error"],
                },
            },
            "rate_limiting": {
                "description": "Built-in rate limit handling",
                "limits": {
                    "openai": "10000 requests/min",
                    "anthropic": "1000 requests/min",
                    "google": "60 requests/min",
                },
                "handling": "Token bucket with automatic throttling",
            },
            "best_practices": [
                "Use model tiers based on task complexity",
                "Implement cost budgets for evaluations",
                "Cache model responses when appropriate",
                "Monitor fallback frequency for optimization",
                "Use temperature=0 for consistent evaluations",
                "Batch requests to reduce overhead",
                "Set appropriate max_tokens limits",
            ],
        }
        return Response(guide)


class ModelSelectionExamplesView(APIView):
    """
    Examples of model selection strategies and configurations.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        """Get model selection examples for various use cases."""
        examples = {
            "use_cases": {
                "binary_classification": {
                    "description": "Simple yes/no evaluations",
                    "recommended_tier": "FAST",
                    "primary_models": ["gpt-3.5-turbo", "mistral-7b"],
                    "fallback_models": ["claude-instant", "llama-2-7b"],
                    "configuration": {
                        "temperature": 0,
                        "max_tokens": 10,
                        "prompt_template": "Answer yes or no: {question}",
                    },
                    "expected_cost": "$0.001 per evaluation",
                },
                "scoring": {
                    "description": "Numeric scoring (1-10 scale)",
                    "recommended_tier": "FAST",
                    "primary_models": ["gpt-3.5-turbo", "claude-instant"],
                    "fallback_models": ["mistral-7b"],
                    "configuration": {
                        "temperature": 0,
                        "max_tokens": 50,
                        "prompt_template": "Rate on a scale of 1-10: {content}\nScore:",
                    },
                    "expected_cost": "$0.002 per evaluation",
                },
                "code_review": {
                    "description": "Technical code quality assessment",
                    "recommended_tier": "BALANCED",
                    "primary_models": ["gpt-4", "claude-2"],
                    "fallback_models": ["gpt-3.5-turbo-16k"],
                    "configuration": {
                        "temperature": 0.3,
                        "max_tokens": 500,
                        "prompt_template": "Review this code for quality:\n{code}\n\nIssues found:",
                    },
                    "expected_cost": "$0.05 per evaluation",
                },
                "content_moderation": {
                    "description": "Safety and appropriateness checks",
                    "recommended_tier": "FAST",
                    "primary_models": ["gpt-3.5-turbo", "claude-instant"],
                    "fallback_models": ["mistral-7b"],
                    "configuration": {
                        "temperature": 0,
                        "max_tokens": 100,
                        "prompt_template": "Is this content safe and appropriate?\n{content}\n\nIssues:",
                    },
                    "expected_cost": "$0.003 per evaluation",
                },
                "creative_writing": {
                    "description": "Evaluate creative content quality",
                    "recommended_tier": "QUALITY",
                    "primary_models": ["gpt-4-turbo", "claude-3-opus"],
                    "fallback_models": ["gpt-4"],
                    "configuration": {
                        "temperature": 0.5,
                        "max_tokens": 1000,
                        "prompt_template": "Evaluate this creative writing:\n{content}\n\nDetailed analysis:",
                    },
                    "expected_cost": "$0.15 per evaluation",
                },
                "translation_quality": {
                    "description": "Assess translation accuracy and fluency",
                    "recommended_tier": "BALANCED",
                    "primary_models": ["gpt-4", "gemini-pro"],
                    "fallback_models": ["gpt-3.5-turbo"],
                    "configuration": {
                        "temperature": 0.2,
                        "max_tokens": 300,
                        "prompt_template": "Evaluate translation quality:\nSource: {source}\nTranslation: {translation}\n\nAssessment:",
                    },
                    "expected_cost": "$0.03 per evaluation",
                },
                "reasoning_tasks": {
                    "description": "Complex logical reasoning evaluation",
                    "recommended_tier": "QUALITY",
                    "primary_models": ["gpt-4-turbo", "claude-3-opus", "gemini-ultra"],
                    "fallback_models": ["gpt-4"],
                    "configuration": {
                        "temperature": 0.1,
                        "max_tokens": 2000,
                        "prompt_template": "Evaluate the reasoning:\n{reasoning}\n\nStep-by-step analysis:",
                    },
                    "expected_cost": "$0.20 per evaluation",
                },
            },
            "selection_strategy": {
                "factors_to_consider": [
                    "Task complexity",
                    "Required accuracy",
                    "Budget constraints",
                    "Latency requirements",
                    "Token limits",
                ],
                "decision_tree": {
                    "1": "Is it a simple binary/categorical task? → Use FAST tier",
                    "2": "Does it require reasoning or analysis? → Use BALANCED tier",
                    "3": "Is it creative or highly complex? → Use QUALITY tier",
                    "4": "Is cost a primary concern? → Start with FAST, upgrade if needed",
                    "5": "Need consistent results? → Use temperature=0",
                },
            },
            "optimization_tips": [
                "Start with cheaper models and validate quality",
                "Use sampling on subset before full evaluation",
                "Cache results for repeated evaluations",
                "Batch similar evaluations together",
                "Monitor actual vs estimated costs",
                "Track model performance metrics",
                "Adjust prompts to reduce token usage",
            ],
        }
        return Response(examples)


class CostEstimationExamplesView(APIView):
    """
    Examples of cost estimation for different evaluation scenarios.
    """

    permission_classes = []
    authentication_classes = []

    def get(self, request):
        """Get cost estimation examples for different scenarios."""
        examples = {
            "scenarios": {
                "small_evaluation": {
                    "description": "Quick validation on small dataset",
                    "dataset_size": 100,
                    "model": "gpt-3.5-turbo",
                    "prompt_tokens_per_sample": 200,
                    "completion_tokens_per_sample": 50,
                    "calculation": {
                        "total_prompt_tokens": 20000,
                        "total_completion_tokens": 5000,
                        "prompt_cost": "$0.02",
                        "completion_cost": "$0.01",
                        "total_cost": "$0.03",
                    },
                    "optimization": "Perfect for quick experiments",
                },
                "medium_evaluation": {
                    "description": "Standard evaluation run",
                    "dataset_size": 1000,
                    "model": "gpt-4",
                    "prompt_tokens_per_sample": 500,
                    "completion_tokens_per_sample": 200,
                    "calculation": {
                        "total_prompt_tokens": 500000,
                        "total_completion_tokens": 200000,
                        "prompt_cost": "$15.00",
                        "completion_cost": "$12.00",
                        "total_cost": "$27.00",
                    },
                    "optimization": "Consider sampling or BALANCED tier",
                },
                "large_evaluation": {
                    "description": "Full production evaluation",
                    "dataset_size": 10000,
                    "model": "gpt-3.5-turbo",
                    "prompt_tokens_per_sample": 300,
                    "completion_tokens_per_sample": 100,
                    "calculation": {
                        "total_prompt_tokens": 3000000,
                        "total_completion_tokens": 1000000,
                        "prompt_cost": "$3.00",
                        "completion_cost": "$2.00",
                        "total_cost": "$5.00",
                    },
                    "optimization": "Cost-effective for large-scale",
                },
                "multi_criteria": {
                    "description": "Complex rubric with 5 criteria",
                    "dataset_size": 500,
                    "criteria_count": 5,
                    "model": "gpt-4",
                    "tokens_per_criterion": 300,
                    "calculation": {
                        "evaluations": 2500,
                        "total_tokens": 750000,
                        "total_cost": "$45.00",
                    },
                    "optimization": "Use mixed model tiers per criterion",
                },
            },
            "cost_breakdown": {
                "model_pricing": {
                    "gpt-3.5-turbo": {
                        "prompt": "$0.001 per 1K tokens",
                        "completion": "$0.002 per 1K tokens",
                    },
                    "gpt-4": {
                        "prompt": "$0.03 per 1K tokens",
                        "completion": "$0.06 per 1K tokens",
                    },
                    "gpt-4-turbo": {
                        "prompt": "$0.01 per 1K tokens",
                        "completion": "$0.03 per 1K tokens",
                    },
                    "claude-instant": {
                        "prompt": "$0.0008 per 1K tokens",
                        "completion": "$0.0024 per 1K tokens",
                    },
                    "claude-2": {
                        "prompt": "$0.008 per 1K tokens",
                        "completion": "$0.024 per 1K tokens",
                    },
                    "claude-3-opus": {
                        "prompt": "$0.015 per 1K tokens",
                        "completion": "$0.075 per 1K tokens",
                    },
                },
                "token_estimation": {
                    "rule_of_thumb": "1 token ≈ 4 characters",
                    "typical_prompt": "200-500 tokens",
                    "typical_completion": "50-200 tokens",
                    "factors": [
                        "Prompt complexity",
                        "Expected response length",
                        "Number of examples in prompt",
                        "Output format requirements",
                    ],
                },
            },
            "optimization_strategies": {
                "sampling": {
                    "description": "Evaluate subset before full run",
                    "reduction": "80-90% cost savings",
                    "example": "Test on 100 samples → Scale to 10,000",
                },
                "tiered_evaluation": {
                    "description": "Use different models for different criteria",
                    "reduction": "40-60% cost savings",
                    "example": "Simple checks with GPT-3.5, complex with GPT-4",
                },
                "prompt_optimization": {
                    "description": "Reduce prompt size without losing context",
                    "reduction": "20-30% cost savings",
                    "example": "Remove redundant instructions, use concise formats",
                },
                "caching": {
                    "description": "Cache and reuse evaluations",
                    "reduction": "Variable based on dataset overlap",
                    "example": "Cache common test cases across runs",
                },
                "batch_processing": {
                    "description": "Process multiple samples in one request",
                    "reduction": "10-15% overhead reduction",
                    "example": "Batch 10 samples per API call",
                },
            },
            "budget_planning": {
                "recommended_approach": [
                    "1. Start with cost estimation endpoint",
                    "2. Run pilot on 1% of dataset",
                    "3. Validate quality meets requirements",
                    "4. Adjust model selection if needed",
                    "5. Set cost budget limits",
                    "6. Monitor actual vs estimated costs",
                ],
                "cost_controls": {
                    "hard_limit": "Set maximum cost per run",
                    "soft_limit": "Warning at 80% of budget",
                    "auto_downgrade": "Switch to cheaper models if over budget",
                    "sampling": "Automatically sample if dataset too large",
                },
            },
        }
        return Response(examples)