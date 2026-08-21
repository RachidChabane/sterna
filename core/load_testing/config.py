"""
Load Testing Configuration.

Defines test configurations, performance baselines, and environment settings.
"""

import os
from enum import Enum
from typing import Dict, Any


class LoadProfile(Enum):
    """Predefined load testing profiles."""

    SMOKE = "smoke"  # Quick test to verify functionality
    LOAD = "load"  # Standard load test
    STRESS = "stress"  # Test system limits
    SPIKE = "spike"  # Test sudden traffic increases
    ENDURANCE = "endurance"  # Long-running stability test


class TestConfig:
    """Load testing configuration."""

    # Environment settings
    BASE_URL = os.getenv("LOAD_TEST_BASE_URL", "http://localhost:8000")
    API_PREFIX = "/api"

    # Authentication settings
    TEST_USERNAME = os.getenv("LOAD_TEST_USERNAME", "loadtest@example.com")
    TEST_PASSWORD = os.getenv("LOAD_TEST_PASSWORD", "TestPassword123!")

    # Test data settings
    DATASET_SIZE_RANGE = (100, 1000)  # Min and max samples in test datasets
    RUBRIC_CRITERIA_RANGE = (3, 10)  # Min and max criteria in test rubrics
    EVALUATION_BATCH_SIZE = 50  # Samples per evaluation run

    # Performance baselines (in milliseconds)
    PERFORMANCE_BASELINES = {
        "auth_login": {"p50": 100, "p95": 500, "p99": 1000},
        "dataset_list": {"p50": 50, "p95": 200, "p99": 500},
        "dataset_create": {"p50": 200, "p95": 800, "p99": 2000},
        "dataset_import": {"p50": 500, "p95": 2000, "p99": 5000},
        "rubric_create": {"p50": 150, "p95": 600, "p99": 1500},
        "evaluation_create": {"p50": 300, "p95": 1200, "p99": 3000},
        "evaluation_run": {"p50": 1000, "p95": 5000, "p99": 10000},
        "webhook_trigger": {"p50": 50, "p95": 200, "p99": 500},
        "metrics_query": {"p50": 100, "p95": 400, "p99": 1000},
    }

    # Load profiles configuration
    LOAD_PROFILES: Dict[LoadProfile, Dict[str, Any]] = {
        LoadProfile.SMOKE: {
            "users": 1,
            "spawn_rate": 1,
            "run_time": "30s",
            "wait_time": (1, 2),
        },
        LoadProfile.LOAD: {
            "users": 100,
            "spawn_rate": 10,
            "run_time": "5m",
            "wait_time": (1, 3),
        },
        LoadProfile.STRESS: {
            "users": 500,
            "spawn_rate": 50,
            "run_time": "10m",
            "wait_time": (0.5, 2),
        },
        LoadProfile.SPIKE: {
            "users": 1000,
            "spawn_rate": 100,
            "run_time": "2m",
            "wait_time": (0.5, 1),
        },
        LoadProfile.ENDURANCE: {
            "users": 50,
            "spawn_rate": 5,
            "run_time": "1h",
            "wait_time": (2, 5),
        },
    }

    # API endpoints to test
    API_ENDPOINTS = {
        "health": "/health/",
        "api_health": "/api/health/",
        # Authentication
        "login": "/api/auth/login/",
        "refresh": "/api/auth/refresh/",
        "logout": "/api/auth/logout/",
        # Projects
        "projects": "/api/projects/",
        "project_detail": "/api/projects/{project_id}/",
        # Datasets
        "datasets": "/api/datasets/",
        "dataset_detail": "/api/datasets/{dataset_id}/",
        "dataset_samples": "/api/datasets/{dataset_id}/samples/",
        "dataset_import": "/api/datasets/import/",
        # Rubrics
        "rubrics": "/api/rubrics/",
        "rubric_detail": "/api/rubrics/{rubric_id}/",
        "rubric_criteria": "/api/rubrics/{rubric_id}/criteria/",
        # Evaluations
        "evaluations": "/api/evaluations/runs/",
        "evaluation_detail": "/api/evaluations/runs/{run_id}/",
        "evaluation_results": "/api/evaluations/runs/{run_id}/results/",
        # Monitoring
        "metrics_summary": "/api/monitoring/metrics/summary/",
        "metrics_models": "/api/monitoring/metrics/models/",
        "metrics_anomalies": "/api/monitoring/metrics/anomalies/",
        # Webhooks
        "webhooks": "/api/webhooks/",
        "webhook_test": "/api/webhooks/{webhook_id}/test/",
    }

    # Request timeout settings
    REQUEST_TIMEOUT = 30  # seconds

    # Rate limiting settings
    RATE_LIMIT_REQUESTS = 100  # requests per minute

    # Data generation seeds for reproducibility
    RANDOM_SEED = 42

    @classmethod
    def get_full_url(cls, endpoint: str, **kwargs) -> str:
        """Get full URL for an endpoint."""
        if endpoint in cls.API_ENDPOINTS:
            path = cls.API_ENDPOINTS[endpoint]
            if kwargs:
                path = path.format(**kwargs)
            return cls.BASE_URL + path
        return cls.BASE_URL + endpoint

    @classmethod
    def get_profile(cls, profile: LoadProfile) -> Dict[str, Any]:
        """Get configuration for a specific load profile."""
        return cls.LOAD_PROFILES.get(profile, cls.LOAD_PROFILES[LoadProfile.LOAD])
