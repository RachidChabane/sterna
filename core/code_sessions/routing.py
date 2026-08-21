"""WebSocket URL routing for code sessions."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/code/jobs/$", consumers.CodeJobConsumer.as_asgi()),
]
