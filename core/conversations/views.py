"""
Views for conversation API endpoints.

Provides ViewSets for Conversation, Chat, and Message models
with proper permission handling and query optimization.
"""

import logging
from decimal import Decimal

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Conversation, Chat, Message
from workspaces.models import Asset, WorkspaceFile
from workspaces.services.workspace_storage import get_storage_service
from .serializers import (
    ConversationSerializer,
    ConversationListSerializer,
    ConversationCreateSerializer,
    ConversationUpdateSerializer,
    ConversationDetailSerializer,
    ChatSerializer,
    ChatListSerializer,
    ChatCreateSerializer,
    MessageSerializer,
    MessageCreateSerializer,
    BulkMessageCreateSerializer,
)

logger = logging.getLogger(__name__)


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Conversation CRUD operations.

    Endpoints:
    - GET /conversations/ - List user's conversations
    - POST /conversations/ - Create new conversation
    - GET /conversations/{id}/ - Get conversation detail with chats/messages
    - PATCH /conversations/{id}/ - Update conversation
    - DELETE /conversations/{id}/ - Delete conversation
    - POST /conversations/{id}/archive/ - Archive conversation
    - POST /conversations/{id}/unarchive/ - Unarchive conversation
    - POST /conversations/{id}/pin/ - Pin conversation
    - POST /conversations/{id}/unpin/ - Unpin conversation
    """

    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['updated_at', 'created_at', 'last_message_at', 'name']
    ordering = ['-updated_at']

    def get_queryset(self):
        """Filter conversations to only those owned by the current user."""
        queryset = Conversation.objects.filter(user=self.request.user)

        # Annotate with counts for efficiency
        queryset = queryset.annotate(
            _message_count=Count('chats__messages', distinct=True),
            _chat_count=Count('chats', distinct=True),
        )

        # Prefetch chats for list view (needed for chat_models in serializer)
        # Must explicitly order by position since prefetch doesn't use model's default ordering
        if self.action == 'list':
            queryset = queryset.prefetch_related(
                Prefetch('chats', queryset=Chat.objects.order_by('position', 'created_at'))
            )

        # Filter by archived status
        is_archived = self.request.query_params.get('is_archived')
        if is_archived is not None:
            queryset = queryset.filter(is_archived=is_archived.lower() == 'true')

        # Filter by pinned status
        is_pinned = self.request.query_params.get('is_pinned')
        if is_pinned is not None:
            queryset = queryset.filter(is_pinned=is_pinned.lower() == 'true')

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return ConversationListSerializer
        elif self.action == 'create':
            return ConversationCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ConversationUpdateSerializer
        elif self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationSerializer

    def get_object(self):
        """Get conversation with optimized queries for detail view."""
        queryset = self.get_queryset()

        if self.action == 'retrieve':
            # Prefetch chats and messages for detail view
            # Must explicitly order by position since Prefetch doesn't use model's default ordering
            queryset = queryset.prefetch_related(
                Prefetch(
                    'chats',
                    queryset=Chat.objects.annotate(
                        _message_count=Count('messages')
                    ).prefetch_related('messages').order_by('position', 'created_at')
                )
            )

        pk = self.kwargs.get('pk')
        obj = get_object_or_404(queryset, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Archive a conversation."""
        conversation = self.get_object()
        conversation.is_archived = True
        conversation.save(update_fields=['is_archived', 'updated_at'])
        return Response({'status': 'archived'})

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        """Unarchive a conversation."""
        conversation = self.get_object()
        conversation.is_archived = False
        conversation.save(update_fields=['is_archived', 'updated_at'])
        return Response({'status': 'unarchived'})

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        """Pin a conversation."""
        conversation = self.get_object()
        conversation.is_pinned = True
        conversation.save(update_fields=['is_pinned', 'updated_at'])
        return Response({'status': 'pinned'})

    @action(detail=True, methods=['post'])
    def unpin(self, request, pk=None):
        """Unpin a conversation."""
        conversation = self.get_object()
        conversation.is_pinned = False
        conversation.save(update_fields=['is_pinned', 'updated_at'])
        return Response({'status': 'unpinned'})

    @action(detail=True, methods=['post'])
    def generate_name(self, request, pk=None):
        """Generate name from first user message."""
        conversation = self.get_object()
        if not conversation.is_custom_name:
            conversation.name = conversation.generate_name_from_messages()
            conversation.save(update_fields=['name', 'updated_at'])
        serializer = ConversationListSerializer(conversation)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """
        Search conversations by message content.

        Query params:
        - q: Search query (required, min 2 chars)
        - page: Page number (default 1)
        - page_size: Results per page (default 20, max 100)
        """
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response(
                {'error': 'Query parameter "q" is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Minimum query length to prevent expensive broad searches
        if len(query) < 2:
            return Response(
                {'error': 'Query must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Safe parameter parsing with defaults
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        try:
            page_size = min(max(1, int(request.query_params.get('page_size', 20))), 100)
        except (ValueError, TypeError):
            page_size = 20

        # Single optimized query using Q objects for OR condition
        # This searches both JSON content (content__text) and plain string content
        messages = Message.objects.filter(
            chat__conversation__user=request.user
        ).filter(
            Q(content__text__icontains=query) |  # JSON content with text field
            Q(content__icontains=query)          # Plain string content
        ).select_related(
            'chat__conversation'
        ).order_by('-created_at').only(
            'id', 'content', 'role', 'model_id', 'model_provider', 'created_at',
            'chat__conversation_id',
            'chat__conversation__id', 'chat__conversation__name',
            'chat__conversation__created_at', 'chat__conversation__updated_at',
            'chat__conversation__is_archived', 'chat__conversation__is_pinned'
        )

        # Group by conversation, keeping first (most recent) match per conversation
        seen_conversations = {}
        # Limit scan to prevent excessive processing
        for msg in messages[:500]:
            conv_id = str(msg.chat.conversation_id)
            if conv_id not in seen_conversations:
                seen_conversations[conv_id] = {
                    'conversation': msg.chat.conversation,
                    'matching_message': msg,
                    'snippet': self._extract_snippet(msg.content, query)
                }
                # Early exit once we have enough unique conversations
                if len(seen_conversations) >= 100:
                    break

        # Paginate results
        results = list(seen_conversations.values())
        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size
        paginated = results[start:end]

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': [
                {
                    'conversation': ConversationListSerializer(r['conversation']).data,
                    'snippet': r['snippet'],
                    'message_role': r['matching_message'].role,
                    'message_model_id': r['matching_message'].model_id,
                    'message_model_provider': r['matching_message'].model_provider,
                    'message_created_at': r['matching_message'].created_at.isoformat(),
                }
                for r in paginated
            ]
        })

    def _extract_snippet(self, content, query, max_length=150):
        """Extract a snippet around the matching text."""
        # Handle various content formats
        if isinstance(content, dict):
            text = content.get('text', '')
        elif isinstance(content, str):
            text = content
        else:
            text = str(content)

        if not text:
            return ''

        query_lower = query.lower()
        text_lower = text.lower()

        pos = text_lower.find(query_lower)
        if pos == -1:
            return text[:max_length] + '...' if len(text) > max_length else text

        # Get context around match
        start = max(0, pos - 50)
        end = min(len(text), pos + len(query) + 100)

        snippet = text[start:end]
        if start > 0:
            snippet = '...' + snippet
        if end < len(text):
            snippet = snippet + '...'

        return snippet

    def perform_destroy(self, instance):
        """
        Delete conversation and clean up R2 storage.

        Deletes all R2-stored assets and workspace files before
        letting Django cascade delete the database records.
        """
        import logging
        logger = logging.getLogger(__name__)

        storage_service = get_storage_service()

        # Delete R2-stored assets (images, videos, files)
        # Assets are now linked via Chat, not directly to Conversation
        r2_assets = Asset.objects.filter(
            chat__conversation=instance,
            storage_type=Asset.STORAGE_R2,
            r2_key__isnull=False
        )
        for asset in r2_assets:
            if asset.r2_key:
                success = storage_service._delete_from_r2(asset.r2_key)
                if success:
                    logger.info(f"Deleted asset from R2: {asset.r2_key}")
                else:
                    logger.warning(f"Failed to delete asset from R2: {asset.r2_key}")

        # Delete R2-stored workspace files (IDE files)
        # Workspaces are now linked via Chat, not directly to Conversation
        r2_files = WorkspaceFile.objects.filter(
            workspace__chat__conversation=instance,
            storage_type=WorkspaceFile.STORAGE_R2,
            r2_key__isnull=False
        )
        for file in r2_files:
            if file.r2_key:
                success = storage_service._delete_from_r2(file.r2_key)
                if success:
                    logger.info(f"Deleted workspace file from R2: {file.r2_key}")
                else:
                    logger.warning(f"Failed to delete workspace file from R2: {file.r2_key}")

        # Let Django cascade delete the database records
        instance.delete()

    @action(detail=True, methods=['post'])
    def save_to_knowledge_base(self, request, pk=None):
        """
        Export conversation to knowledge base as a markdown document.

        Formats all messages (excluding tool messages and assets) into a
        readable markdown document and adds it to the user's knowledge base.

        Returns:
            document_id: ID of the created knowledge document
            filename: Generated filename
            status: Document processing status
        """
        import io
        from django.core.files.uploadedfile import InMemoryUploadedFile

        # Import knowledge base services
        try:
            from knowledge_base.services.upload import DocumentUploadService
        except ImportError:
            return Response(
                {'error': 'Knowledge base module not available'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        conversation = self.get_object()

        # Fetch all messages from all chats, ordered properly
        messages = Message.objects.filter(
            chat__conversation=conversation
        ).exclude(
            role='tool'  # Exclude tool messages
        ).select_related('chat').order_by(
            'chat__position', 'chat__created_at', 'sequence', 'created_at'
        )

        if not messages.exists():
            return Response(
                {'error': 'Conversation has no messages to export'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Format conversation as markdown
        markdown_content = self._format_conversation_as_markdown(conversation, messages)

        # Generate filename
        safe_name = ''.join(c if c.isalnum() or c in ' -_' else '' for c in conversation.name)
        safe_name = safe_name[:50].strip() or 'conversation'
        timestamp = timezone.now().strftime('%Y%m%d')
        filename = f"{safe_name}_{timestamp}.md"

        # Create in-memory file
        content_bytes = markdown_content.encode('utf-8')
        file_obj = InMemoryUploadedFile(
            file=io.BytesIO(content_bytes),
            field_name='file',
            name=filename,
            content_type='text/markdown',
            size=len(content_bytes),
            charset='utf-8'
        )

        # Upload to knowledge base
        upload_service = DocumentUploadService()
        try:
            tags = ['conversation']
            document = upload_service.upload(
                user=request.user,
                file=file_obj,
                tags=tags
            )
            return Response({
                'document_id': str(document.id),
                'filename': document.filename,
                'status': document.status,
                'message': 'Conversation saved to knowledge base'
            }, status=status.HTTP_201_CREATED)

        except DocumentUploadService.StorageLimitExceeded:
            return Response(
                {'error': 'Storage limit exceeded. Please delete some documents first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except DocumentUploadService.DuplicateDocument as e:
            return Response({
                'error': 'This conversation has already been saved to the knowledge base',
                'existing_document_id': str(e.existing_id),
                'existing_filename': e.existing_filename
            }, status=status.HTTP_409_CONFLICT)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception(f"Failed to save conversation to knowledge base: {e}")
            return Response(
                {'error': 'Failed to save conversation to knowledge base'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _format_conversation_as_markdown(self, conversation, messages):
        """Format conversation messages as a readable markdown document."""
        import re
        # Pattern to match {{ACTION:...}} blocks
        action_pattern = re.compile(r'\{\{ACTION:[^}]*\}\}')

        lines = []

        # Header
        lines.append(f"# {conversation.name}")
        lines.append("")
        lines.append(f"**Created:** {conversation.created_at.strftime('%B %d, %Y at %H:%M')}")
        if conversation.updated_at:
            lines.append(f"**Last updated:** {conversation.updated_at.strftime('%B %d, %Y at %H:%M')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Messages
        current_chat_id = None
        for msg in messages:
            # Add chat separator if switching chats
            if current_chat_id is not None and msg.chat_id != current_chat_id:
                lines.append("")
                lines.append("---")
                lines.append("")

            current_chat_id = msg.chat_id

            # Format role with model info for assistant messages
            if msg.role == 'user':
                role_label = "**User:**"
            elif msg.role == 'assistant':
                # Include model name for assistant messages
                model_name = msg.model_id or msg.model_provider or 'Assistant'
                role_label = f"**{model_name}:**"
            elif msg.role == 'system':
                role_label = "**System:**"
            else:
                role_label = f"**{msg.role.title()}:**"

            # Extract text content
            content = msg.content
            if isinstance(content, dict):
                text = content.get('text', '')
            elif isinstance(content, str):
                text = content
            else:
                text = str(content) if content else ''

            # Strip {{ACTION:...}} blocks from text
            text = action_pattern.sub('', text).strip()

            # Skip empty messages
            if not text:
                continue

            lines.append(role_label)
            lines.append("")
            lines.append(text)
            lines.append("")

        return '\n'.join(lines)


class ChatViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Chat CRUD operations.

    Nested under conversation: /conversations/{conversation_id}/chats/

    Endpoints:
    - GET /conversations/{conversation_id}/chats/ - List chats in conversation
    - POST /conversations/{conversation_id}/chats/ - Create new chat
    - GET /conversations/{conversation_id}/chats/{id}/ - Get chat with messages
    - PATCH /conversations/{conversation_id}/chats/{id}/ - Update chat
    - DELETE /conversations/{conversation_id}/chats/{id}/ - Delete chat
    """

    permission_classes = [IsAuthenticated]

    def get_conversation(self):
        """Get parent conversation, ensuring user owns it."""
        conversation_id = self.kwargs.get('conversation_pk')
        return get_object_or_404(
            Conversation,
            pk=conversation_id,
            user=self.request.user
        )

    def get_queryset(self):
        """Filter chats to those in the parent conversation."""
        conversation = self.get_conversation()
        queryset = Chat.objects.filter(conversation=conversation)

        # Annotate with message count
        queryset = queryset.annotate(
            _message_count=Count('messages')
        )

        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return ChatListSerializer
        elif self.action == 'create':
            return ChatCreateSerializer
        elif self.action == 'retrieve':
            return ChatSerializer
        return ChatSerializer

    def get_object(self):
        """Get chat with messages for detail view."""
        queryset = self.get_queryset()

        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('messages')

        pk = self.kwargs.get('pk')
        obj = get_object_or_404(queryset, pk=pk)
        return obj

    def perform_create(self, serializer):
        """Create chat in the parent conversation."""
        conversation = self.get_conversation()
        serializer.save(conversation=conversation)

    def create(self, request, *args, **kwargs):
        """Create a new chat and return it with full serializer (including id)."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Return the created chat using ChatSerializer (which includes id)
        # instead of ChatCreateSerializer (which doesn't)
        chat = serializer.instance
        response_serializer = ChatSerializer(chat)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class MessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Message CRUD operations.

    Nested under chat: /conversations/{conversation_id}/chats/{chat_id}/messages/

    Endpoints:
    - GET .../messages/ - List messages in chat
    - POST .../messages/ - Create new message
    - POST .../messages/bulk/ - Create multiple messages
    - GET .../messages/{id}/ - Get message detail
    - PATCH .../messages/{id}/ - Update message
    - DELETE .../messages/{id}/ - Delete message
    """

    permission_classes = [IsAuthenticated]

    def get_chat(self):
        """Get parent chat, ensuring user owns the conversation."""
        conversation_id = self.kwargs.get('conversation_pk')
        chat_id = self.kwargs.get('chat_pk')

        conversation = get_object_or_404(
            Conversation,
            pk=conversation_id,
            user=self.request.user
        )
        return get_object_or_404(Chat, pk=chat_id, conversation=conversation)

    def get_queryset(self):
        """Filter messages to those in the parent chat."""
        chat = self.get_chat()
        return Message.objects.filter(chat=chat).order_by('sequence')

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return MessageCreateSerializer
        elif self.action == 'bulk_create':
            return BulkMessageCreateSerializer
        return MessageSerializer

    def perform_create(self, serializer):
        """Create message in the parent chat."""
        chat = self.get_chat()
        serializer.save(chat=chat)

    # Headroom multiplier over catalog token pricing when clamping a
    # client-claimed stopped-message cost (covers reasoning tokens,
    # provider fees and pricing drift without trusting the raw claim).
    STOPPED_COST_CLAMP_FACTOR = Decimal('2')

    def perform_update(self, serializer):
        """Update message. If billing data is patched on a stopped message,
        settle usage server-side.

        The client PATCH is ADVISORY: the claimed cost is never recorded
        verbatim. It is replaced by the server-proxied OpenRouter
        generation lookup when generation ids are available in the message
        metadata, otherwise clamped to a bound derived from the model's
        catalog pricing and the claimed token counts. When the stream view
        already enqueued a server-side abort settlement
        (llm.tasks.settle_aborted_generations) for this chat, the PATCH
        records nothing — the settlement task owns billing.
        """
        instance = serializer.save()

        # Check if this is a billing update for a stopped message
        cost = self.request.data.get('cost')
        prompt_tokens = self.request.data.get('prompt_tokens')
        if instance.is_stopped and cost and prompt_tokens:
            try:
                self._settle_stopped_message_billing(instance)
            except Exception as e:
                logger.warning(f"Failed to record stopped message usage: {e}")

    def _settle_stopped_message_billing(self, instance):
        """Record clamped usage for a client-PATCHed stopped message."""
        from django.core.cache import cache

        from usage_quota.billing import get_billing_service, BillableOperation
        from usage_quota.models import ServiceType, FeatureType

        data = self.request.data
        user = self.request.user
        try:
            claimed_cost = Decimal(str(data.get('cost')))
            claimed_prompt_tokens = int(data.get('prompt_tokens') or 0)
            claimed_completion_tokens = int(data.get('completion_tokens', 0) or 0)
        except (ArithmeticError, TypeError, ValueError):
            logger.warning(
                "billing.stopped_settlement_rejected",
                extra={
                    "user_id": str(user.id),
                    "message_id": str(instance.id),
                    "reason": "unparseable_billing_fields",
                },
            )
            return
        if claimed_cost < 0 or claimed_prompt_tokens < 0 or claimed_completion_tokens < 0:
            logger.warning(
                "billing.stopped_settlement_rejected",
                extra={
                    "user_id": str(user.id),
                    "message_id": str(instance.id),
                    "reason": "negative_values",
                },
            )
            return

        def _log_settlement(accepted, source):
            logger.info(
                "billing.stopped_settlement",
                extra={
                    "user_id": str(user.id),
                    "message_id": str(instance.id),
                    "chat_id": str(instance.chat_id),
                    "model_id": instance.model_id or '',
                    "client_claimed_cost": str(claimed_cost),
                    "accepted_cost": str(accepted),
                    "accepted_source": source,
                },
            )

        # 1) Server-side abort settlement pending/complete for this chat?
        #    Then the Celery task owns billing — record nothing here.
        try:
            from llm.tasks import ABORT_SETTLEMENT_CACHE_KEY
            marker = cache.get(
                ABORT_SETTLEMENT_CACHE_KEY.format(chat_id=str(instance.chat_id))
            )
        except Exception:
            marker = None
        if marker:
            _log_settlement(Decimal('0'), 'server_settlement_owns_billing')
            return

        billing = get_billing_service()

        # 2) Preferred: replace the claim with the server-verified cost via
        #    the OpenRouter generation lookup (generation ids stored in the
        #    message metadata by newer clients).
        generation_ids = []
        if isinstance(instance.metadata, dict):
            generation_ids = [
                g for g in (instance.metadata.get('generation_ids') or []) if g
            ]
        verified = self._verified_generation_usage(user, generation_ids)
        if verified is not None:
            accepted_cost, verified_prompt, verified_completion, unsettled_ids = verified
            if accepted_cost <= 0:
                _log_settlement(Decimal('0'), 'generation_lookup_already_settled')
                return
            billing.record_usage(
                user=user,
                operation=BillableOperation(
                    service=ServiceType.OPENROUTER,
                    feature=FeatureType.CHAT,
                    model_id=instance.model_id or '',
                    prompt_tokens=verified_prompt,
                    completion_tokens=verified_completion,
                    cost_usd=accepted_cost,
                    # Tag the settled generation ids so the Celery abort
                    # settlement (idempotent on request_id) skips them.
                    request_id=unsettled_ids[0] if len(unsettled_ids) == 1 else '',
                    extra_data={
                        'stopped_message': True,
                        'message_id': str(instance.id),
                        'client_claimed_cost': str(claimed_cost),
                        'accepted_source': 'generation_lookup',
                        'generation_ids': unsettled_ids,
                    },
                ),
            )
            _log_settlement(accepted_cost, 'generation_lookup')
            return

        # 3) Fallback: clamp the claim to catalog pricing × claimed tokens.
        cap = self._catalog_cost_cap(
            instance.model_id or '', claimed_prompt_tokens, claimed_completion_tokens
        )
        accepted_cost = min(claimed_cost, cap) if cap is not None else claimed_cost
        if cap is None:
            logger.warning(
                "billing.stopped_settlement_no_cap",
                extra={
                    "user_id": str(user.id),
                    "message_id": str(instance.id),
                    "model_id": instance.model_id or '',
                },
            )
        billing.record_usage(
            user=user,
            operation=BillableOperation(
                service=ServiceType.OPENROUTER,
                feature=FeatureType.CHAT,
                model_id=instance.model_id or '',
                prompt_tokens=claimed_prompt_tokens,
                completion_tokens=claimed_completion_tokens,
                cost_usd=accepted_cost,
                extra_data={
                    'stopped_message': True,
                    'message_id': str(instance.id),
                    'client_claimed_cost': str(claimed_cost),
                    'accepted_source': 'catalog_price_clamp',
                },
            ),
        )
        _log_settlement(accepted_cost, 'catalog_price_clamp')

    def _verified_generation_usage(self, user, generation_ids):
        """Sum server-verified usage for unsettled generation ids.

        Returns (cost, prompt_tokens, completion_tokens, unsettled_ids) or
        None when no ids are available / the lookup fails (caller falls
        back to the catalog-price clamp).
        """
        if not generation_ids:
            return None
        try:
            from llm.services.api_key_resolver import get_api_key_for_user
            from llm.tasks import _is_generation_settled, fetch_generation_data

            api_key = get_api_key_for_user(user)
            if not api_key:
                return None

            total_cost = Decimal('0')
            total_prompt = 0
            total_completion = 0
            unsettled = []
            for gen_id in generation_ids:
                if _is_generation_settled(user, gen_id):
                    continue
                gen_data = fetch_generation_data(api_key, gen_id)
                if gen_data is None:
                    # Not finalized yet — the whole lookup is unreliable.
                    return None
                unsettled.append(gen_id)
                total_cost += Decimal(str(gen_data.get('total_cost') or 0))
                total_prompt += gen_data.get('tokens_prompt') or 0
                total_completion += gen_data.get('tokens_completion') or 0
            return total_cost, total_prompt, total_completion, unsettled
        except Exception:
            logger.warning(
                "billing.stopped_settlement_lookup_failed", exc_info=True
            )
            return None

    def _catalog_cost_cap(self, model_id, prompt_tokens, completion_tokens):
        """Upper bound for a stopped message's cost from catalog pricing."""
        try:
            from llm.catalog_service import CatalogService

            details = CatalogService().estimate_cost_detailed(
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            return Decimal(str(details['total_cost'])) * self.STOPPED_COST_CLAMP_FACTOR
        except Exception:
            logger.warning("billing.stopped_settlement_cap_failed", exc_info=True)
            return None

    @action(detail=False, methods=['post'])
    def bulk(self, request, **kwargs):
        """Create multiple messages at once."""
        chat = self.get_chat()
        serializer = BulkMessageCreateSerializer(
            data=request.data,
            context={'chat': chat, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        messages = serializer.save()

        # Update conversation's last_message_at
        if messages:
            Conversation.objects.filter(
                id=chat.conversation_id
            ).update(
                last_message_at=timezone.now(),
                updated_at=timezone.now()
            )

        return Response(
            MessageSerializer(messages, many=True).data,
            status=status.HTTP_201_CREATED
        )
