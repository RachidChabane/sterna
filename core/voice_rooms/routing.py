"""WebSocket URL routing for voice rooms."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/voice-rooms/(?P<room_id>[0-9a-f-]+)/$", consumers.VoiceRoomConsumer.as_asgi()),
]
