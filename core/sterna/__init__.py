"""
Sterna - multi-model AI chat platform
"""

# Import Celery app for background task processing
from .celery import app as celery_app

__all__ = ("celery_app",)

__version__ = "1.0.0"
