"""
URL configuration for conversations API.

URL structure:
- /api/conversations/ - List/create conversations
- /api/conversations/{id}/ - Conversation detail
- /api/conversations/{id}/chats/ - List/create chats
- /api/conversations/{id}/chats/{id}/ - Chat detail
- /api/conversations/{id}/chats/{id}/messages/ - List/create messages
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ConversationViewSet, ChatViewSet, MessageViewSet

# Main router for conversations
router = DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversation')

app_name = 'conversations'

# Nested URL patterns for chats and messages
chat_list = ChatViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
chat_detail = ChatViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})

message_list = MessageViewSet.as_view({
    'get': 'list',
    'post': 'create',
})
message_detail = MessageViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})
message_bulk = MessageViewSet.as_view({
    'post': 'bulk',
})

urlpatterns = [
    # Main conversation routes
    path('', include(router.urls)),

    # Nested chat routes
    path(
        'conversations/<uuid:conversation_pk>/chats/',
        chat_list,
        name='conversation-chats-list'
    ),
    path(
        'conversations/<uuid:conversation_pk>/chats/<uuid:pk>/',
        chat_detail,
        name='conversation-chats-detail'
    ),

    # Nested message routes
    path(
        'conversations/<uuid:conversation_pk>/chats/<uuid:chat_pk>/messages/',
        message_list,
        name='chat-messages-list'
    ),
    path(
        'conversations/<uuid:conversation_pk>/chats/<uuid:chat_pk>/messages/bulk/',
        message_bulk,
        name='chat-messages-bulk'
    ),
    path(
        'conversations/<uuid:conversation_pk>/chats/<uuid:chat_pk>/messages/<uuid:pk>/',
        message_detail,
        name='chat-messages-detail'
    ),
]
