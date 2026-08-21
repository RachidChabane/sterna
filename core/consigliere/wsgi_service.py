"""
WSGI config for Consigliere microservice.

It exposes the WSGI callable as a module-level variable named ``application``.

This is the entry point for running Consigliere as a standalone microservice.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "consigliere.settings_service")

application = get_wsgi_application()
