"""WebSocket consumer for voice room sessions."""

import base64
import json
import logging
from uuid import uuid4

from channels.generic.websocket import AsyncJsonWebsocketConsumer  # type: ignore[import-untyped]
from asgiref.sync import sync_to_async

from .models import VoiceRoom, VoiceRoomSession, VoiceRoomMessage
from .services.orchestrator import VoiceRoomOrchestrator
from .constants import ACTIVE_SESSION_STATUSES

logger = logging.getLogger(__name__)


class VoiceRoomConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for voice room sessions.

    Protocol:
    1. Client connects with JWT token (via query param)
    2. Server validates token and room access
    3. Server initializes STT, TTS, and LLM connections
    4. Bidirectional streaming begins:
       - Client sends: audio_chunk, end_speaking, pause, resume, skip_agent, end_session
       - Server sends: transcript, agent_state, agent_text, agent_audio, turn, error, room_state
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.room_id = None
        self.session_id = None
        self.db_session = None  # VoiceRoomSession model instance
        self.user = None
        self.orchestrator = None
        self._connected = False
        self._agent_id_map = {}  # Map agent UUID string to VoiceRoomAgent

    async def connect(self):
        """Handle WebSocket connection."""
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.user = self.scope.get("user")
        self.session_id = str(uuid4())

        # Check authentication
        if not self.user or not self.user.is_authenticated:
            logger.warning(f"Unauthorized WebSocket connection attempt for room {self.room_id}")
            await self.close(code=4001)
            return

        # Get room and verify access
        try:
            room = await self._get_room()
            if not room:
                logger.warning(f"Room {self.room_id} not found")
                await self.close(code=4004)
                return

            if str(room.user_id) != str(self.user.id):
                logger.warning(f"User {self.user.id} not authorized for room {self.room_id}")
                await self.close(code=4003)
                return

        except Exception as e:
            logger.error(f"Error getting room: {e}")
            await self.close(code=4000)
            return

        # Tier gate (voice_session): refuse the connection when the
        # user's plan disallows voice rooms or they're past the weekly
        # session count. Runs BEFORE we accept the socket so the close
        # frame carries the structured 402 payload.
        if not await self._check_voice_session_quota():
            return

        # Accept connection
        await self.accept()
        self._connected = True

        # Get or create session for this room
        try:
            self.db_session, initial_conversation = await self._get_or_create_session(room)
            self.session_id = str(self.db_session.id)
            logger.info(f"WebSocket connected: room={self.room_id}, session={self.session_id}, user={self.user.id}, messages={len(initial_conversation)}")
        except Exception as e:
            logger.error(f"Failed to get/create session: {e}")
            await self.send_json({
                "type": "error",
                "code": "SESSION_ERROR",
                "message": str(e),
                "recoverable": False,
            })
            await self.close()
            return

        # Send connection confirmation with previous message count
        await self.send_json({
            "type": "connected",
            "room_id": str(self.room_id),
            "session_id": self.session_id,
            "previous_messages": len(initial_conversation),
        })

        # Initialize orchestrator
        try:
            agents = await self._get_agents(room)

            # Build agent ID map for message persistence
            self._agent_id_map = await self._build_agent_id_map(room)

            self.orchestrator = VoiceRoomOrchestrator(
                room_id=str(room.id),
                agents=agents,
                language=room.language,
                max_response_tokens=room.max_response_tokens,
                send_event=self._send_event,
                session_id=self.session_id,
                initial_conversation=initial_conversation,
                save_message=self._save_message,
                room_description=room.description,
                user_name=room.user_name,
                user=self.user,  # Pass user for API key resolution
            )
            await self.orchestrator.start_session()

        except Exception as e:
            logger.error(f"Failed to start orchestrator: {e}")
            await self.send_json({
                "type": "error",
                "code": "SESSION_START_FAILED",
                "message": str(e),
                "recoverable": False,
            })
            await self.close()

    async def disconnect(self, close_code):
        """Handle WebSocket disconnect."""
        self._connected = False
        logger.info(f"WebSocket disconnected: session={self.session_id}, code={close_code}")

        if self.orchestrator:
            # Signal disconnection so orchestrator stops waiting
            self.orchestrator.client_disconnected = True
            await self.orchestrator.cleanup()

    async def receive_json(self, content):
        """Handle incoming JSON messages."""
        event_type = content.get("type")

        try:
            if event_type == "audio_chunk":
                # Mid-session voice_minutes runtime gate: closes the WS
                # when the user passes their plan's per-session minute
                # limit. Cheap (single DB lookup; cached via plan).
                if not await self._check_session_minute_limit():
                    return
                # Decode and process audio
                audio_base64 = content.get("data", "")
                if audio_base64:
                    audio_bytes = base64.b64decode(audio_base64)
                    # Note: Not logging audio chunks to avoid log spam (10 chunks/sec)
                    if self.orchestrator:
                        await self.orchestrator.handle_audio_chunk(audio_bytes)
                    else:
                        logger.warning("No orchestrator to handle audio chunk")

            elif event_type == "end_speaking":
                if self.orchestrator:
                    await self.orchestrator.handle_user_end_speaking()

            elif event_type == "pause":
                if self.orchestrator:
                    await self.orchestrator.pause()

            elif event_type == "resume":
                if self.orchestrator:
                    await self.orchestrator.resume()

            elif event_type == "skip_agent":
                if self.orchestrator:
                    await self.orchestrator.skip_current_agent()

            elif event_type == "end_session":
                await self.close()

            elif event_type == "settings":
                # Update voice processing settings
                if self.orchestrator:
                    await self.orchestrator.update_settings(
                        silence_timeout=content.get("silence_timeout", 2.0),
                        interruption_threshold=content.get("interruption_threshold", 50),
                        allow_interruptions=content.get("allow_interruptions", True),
                    )
                    logger.info(f"Updated voice settings: silence={content.get('silence_timeout')}s, threshold={content.get('interruption_threshold')}%, interruptions={content.get('allow_interruptions')}")

            elif event_type == "audio_playback_complete":
                # Client signals audio playback finished for an agent
                agent_id = content.get("agent_id")
                if self.orchestrator and agent_id:
                    await self.orchestrator.handle_audio_playback_complete(agent_id)
                    logger.info(f"Audio playback complete for agent: {agent_id}")

            elif event_type == "user_interrupt":
                # Client-side VAD detected user speaking during agent playback
                # This is a backup for when Deepgram's VAD doesn't detect speech
                if self.orchestrator:
                    logger.info("User interrupt signal received from client VAD")
                    await self.orchestrator.handle_user_interrupt()

            else:
                logger.warning(f"Unknown event type: {event_type}")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send_json({
                "type": "error",
                "code": "MESSAGE_ERROR",
                "message": str(e),
                "recoverable": True,
            })

    async def receive(self, text_data=None, bytes_data=None):
        """Handle raw incoming messages (for binary audio)."""
        if bytes_data:
            # Handle binary audio directly
            if self.orchestrator:
                await self.orchestrator.handle_audio_chunk(bytes_data)
        elif text_data:
            # Parse JSON
            try:
                content = json.loads(text_data)
                await self.receive_json(content)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received")

    async def _send_event(self, event: dict):
        """Send event to client (callback for orchestrator)."""
        if not self._connected:
            return  # Don't try to send if client disconnected
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"Error sending event: {e}")
            # Mark as disconnected to stop further attempts
            self._connected = False
            if self.orchestrator:
                self.orchestrator.client_disconnected = True

    async def _get_room(self):
        """Get room from database."""
        @sync_to_async
        def get_room():
            try:
                return VoiceRoom.objects.select_related("user").get(id=self.room_id)
            except VoiceRoom.DoesNotExist:
                return None

        return await get_room()

    async def _get_agents(self, room):
        """Get agents for a room."""
        @sync_to_async
        def get_agents():
            agents = []
            for agent in room.agents.filter(is_active=True).order_by("order"):
                agents.append({
                    "id": str(agent.id),
                    "display_name": agent.display_name,
                    "model_id": agent.model_id,
                    "system_prompt": agent.system_prompt,
                    "voice_id": agent.voice_id,
                    "voice_name": agent.voice_name,
                    "voice_settings": agent.voice_settings or {},
                    "order": agent.order,
                })
            return agents

        return await get_agents()

    async def _check_voice_session_quota(self) -> bool:
        """Pre-flight tier gate for connecting WS clients.

        Closes the socket with code 4002 + structured 402 payload on
        denial. Returns ``True`` when the gate passes (no close yet).
        """
        from decimal import Decimal

        from asgiref.sync import sync_to_async
        from usage_quota.billing.service import get_billing_service
        from usage_quota.exceptions import (
            FeatureNotAvailableException,
            QuotaExceededException,
        )
        from usage_quota.models import FeatureType, ServiceType

        try:
            await sync_to_async(get_billing_service().check_quota)(
                user=self.user,
                service=ServiceType.ELEVENLABS_TTS,
                estimated_cost=Decimal('0'),
                feature=FeatureType.VOICE_ROOM,
                feature_name='voice_session',
            )
        except (FeatureNotAvailableException, QuotaExceededException) as exc:
            await self.accept()
            await self.send_json({
                "type": "quota_denied",
                "payload": exc.to_response_dict(),
            })
            await self.close(code=4002)
            return False
        return True

    async def _check_session_minute_limit(self) -> bool:
        """Mid-session voice_minutes runtime gate.

        Called on each audio chunk path. Closes the WS with code 4002
        + structured payload when the session has exceeded the plan's
        voice_room_minutes_per_session_limit.
        """
        if self.db_session is None:
            return True

        @sync_to_async
        def fetch_limit():
            from usage_quota.billing.service import get_billing_service
            from usage_quota.feature_registry import get as get_spec

            plan = get_billing_service().get_user_plan(self.user)
            spec = get_spec('voice_minutes')
            if spec is None or spec.limit_field is None:
                return None
            return getattr(plan, spec.limit_field, None)

        limit = await fetch_limit()
        if limit is None:
            return True

        from django.utils import timezone

        started_at = self.db_session.started_at
        if started_at is None:
            return True
        elapsed_min = (timezone.now() - started_at).total_seconds() / 60
        if elapsed_min >= limit:
            await self.send_json({
                "type": "session_minute_limit_reached",
                "payload": {
                    "limit_minutes": int(limit),
                    "elapsed_minutes": int(elapsed_min),
                },
            })
            await self.close(code=4002)
            return False
        return True

    async def _get_or_create_session(self, room):
        """
        Get the last active session for this room or create a new one.
        Returns (session, initial_conversation) tuple.
        """
        @sync_to_async
        def get_or_create():
            # Look for an existing session that's not ended
            session = VoiceRoomSession.objects.filter(
                room=room,
                status__in=ACTIVE_SESSION_STATUSES
            ).order_by("-started_at").first()

            if not session:
                # Create a new session
                session = VoiceRoomSession.objects.create(
                    room=room,
                    status="idle"
                )
                logger.info(f"Created new session {session.id} for room {room.id}")
                return session, []

            # Load previous messages
            messages = list(session.messages.select_related("agent").order_by("created_at"))
            conversation = []
            for msg in messages:
                conv_msg = {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                }
                if msg.role == "assistant" and msg.agent:
                    conv_msg["agent_id"] = str(msg.agent.id)
                    conv_msg["agent_name"] = msg.agent.display_name
                conversation.append(conv_msg)

            logger.info(f"Resuming session {session.id} with {len(conversation)} messages")
            return session, conversation

        return await get_or_create()

    async def _build_agent_id_map(self, room):
        """Build a map of agent ID strings to VoiceRoomAgent models."""
        @sync_to_async
        def build_map():
            return {
                str(agent.id): agent
                for agent in room.agents.filter(is_active=True)
            }

        return await build_map()

    async def _save_message(self, message_data: dict):
        """Save a message to the database."""
        if not self.db_session:
            logger.warning("Cannot save message: no database session")
            return

        # Capture these in local variables for the sync_to_async closure
        db_session = self.db_session
        agent_id_map = self._agent_id_map

        @sync_to_async
        def save():
            agent = None
            agent_id = message_data.get("agent_id")

            # Debug logging to trace agent lookup
            logger.info(f"[SaveMessage] role={message_data.get('role')}, agent_id={agent_id}")
            logger.info(f"[SaveMessage] agent_id_map keys: {list(agent_id_map.keys())}")

            if agent_id and agent_id in agent_id_map:
                agent = agent_id_map[agent_id]
                logger.info(f"[SaveMessage] Found agent: {agent.display_name}")
            elif agent_id:
                logger.warning(f"[SaveMessage] agent_id '{agent_id}' not found in map!")

            VoiceRoomMessage.objects.create(
                session=db_session,
                agent=agent,
                role=message_data.get("role", "user"),
                content=message_data.get("content", ""),
                model_id=message_data.get("model_id"),
            )
            logger.info(f"Saved {message_data.get('role')} message (agent={agent}) to session {db_session.id}")

        await save()
