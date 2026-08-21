"""
ASGI config for sterna project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sterna.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

# Import WebSocket routing after Django is initialized
from voice_rooms.routing import websocket_urlpatterns as voice_room_patterns
from voice_rooms.middleware import JWTAuthMiddleware
from code_sessions.routing import websocket_urlpatterns as code_session_patterns

# Combine all WebSocket patterns
all_websocket_patterns = voice_room_patterns + code_session_patterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddleware(
            URLRouter(all_websocket_patterns)
        )
    ),
})
