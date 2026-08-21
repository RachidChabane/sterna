"""
API views for Consigliere AI module.
"""

import logging
import json
from decimal import Decimal
from django.http import StreamingHttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction

from .models import (
    ConsiglierSession,
    ConversationAnalysis,
    ModelRecommendation,
    ConsigliereMessage,
)
from .serializers import (
    AnalyzeConversationRequestSerializer,
    ChatMessageRequestSerializer,
    ContinueSessionRequestSerializer,
    ConsiglierSessionSerializer,
    ConsiglierSessionSummarySerializer,
    ConversationAnalysisSerializer,
)
from .services import (
    ConversationAnalyzer,
    AIAnalyzer,
    ConsiglierChatHandler,
    ContextBuilder,
)
from .services.ai_analyzer import ProgressCallback
from llm.exceptions import ContextLimitExceededException
from llm.error_messages import get_user_friendly_error

logger = logging.getLogger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts Decimal objects to float."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class ConsiglierViewSet(viewsets.ViewSet):
    """
    ViewSet for Consigliere AI advisor.

    Provides endpoints for:
    - Analyzing conversations
    - Chatting with Consigliere
    - Getting recommendations
    - Managing sessions
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def analyze(self, request):
        """
        Create a Consigliere session with basic metrics (no AI-generated analysis).

        POST /api/consigliere/analyze/
        {
            "chat_group": { ... },
            "current_model": "anthropic/claude-3-opus",
            "user_preferences": { ... }
        }

        Returns:
            {
                "session_id": "uuid",
                "analysis": { ... } // Contains only basic metrics
            }
        """
        serializer = AnalyzeConversationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        chat_group = data["chat_group"]
        current_model = data["current_model"]
        user_preferences = data.get("user_preferences", {})

        try:
            with transaction.atomic():
                # Create session
                session = ConsiglierSession.objects.create(
                    user=request.user,
                    chat_group_id=chat_group.get("id", "unknown"),
                    chat_group_data=chat_group,
                    current_model_at_start=current_model,
                )

                # Calculate basic metrics only
                analyzer = ConversationAnalyzer()
                metrics = analyzer._calculate_metrics(
                    [msg for chat in chat_group.get("chats", []) for msg in chat.get("messages", [])]
                )

                # Create analysis record with basic metrics only
                # (no conversation_type, insights, detected_needs, or recommendations yet)
                analysis = ConversationAnalysis.objects.create(
                    session=session,
                    conversation_type="",  # Will be filled by AI
                    total_messages=metrics["total_messages"],
                    total_tokens=metrics["total_tokens"],
                    avg_cost_per_message=metrics["avg_cost_per_message"],
                    avg_latency=metrics["avg_latency"],
                    total_cost=metrics["total_cost"],
                    insights=[],  # Will be filled by AI
                    detected_needs={},  # Will be filled by AI
                    user_preferences=user_preferences,
                )

                # Serialize response
                analysis_serializer = ConversationAnalysisSerializer(analysis)

                return Response(
                    {
                        "session_id": session.id,
                        "analysis": analysis_serializer.data,
                    },
                    status=status.HTTP_201_CREATED,
                )

        except Exception as e:
            logger.error(f"Error creating session: {e}", exc_info=True)
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def generate_analysis(self, request, pk=None):
        """
        Generate AI-powered analysis for an existing session.

        POST /api/consigliere/<session_id>/generate_analysis/
        {
            "current_model": "anthropic/claude-3-opus"
        }

        Returns:
            {
                "analysis": { ... } // Full AI-generated analysis with recommendations
            }
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)

            if not hasattr(session, "analysis"):
                return Response(
                    {"error": "No analysis record found for this session"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            current_model = request.data.get("current_model")
            if not current_model:
                return Response(
                    {"error": "current_model is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            with transaction.atomic():
                analysis = session.analysis

                # Get basic metrics
                metrics = {
                    "total_messages": analysis.total_messages,
                    "total_cost": analysis.total_cost,
                    "avg_latency": analysis.avg_latency,
                    "total_tokens": analysis.total_tokens,
                }

                # Generate AI analysis
                ai_analyzer = AIAnalyzer(current_model, user=request.user)
                ai_result = ai_analyzer.analyze_with_ai(
                    chat_group_data=session.chat_group_data,
                    current_model_id=current_model,
                    metrics=metrics,
                )

                # Update analysis record
                analysis.conversation_type = ai_result["conversation_type"]
                analysis.detected_needs = ai_result["detected_needs"]
                analysis.insights = ai_result["insights"]
                analysis.save()

                # Delete old recommendations and create new ones
                analysis.recommendations.all().delete()

                # Create new recommendations from AI (convert Decimal to float)
                for rec in ai_result["recommendations"]:
                    ModelRecommendation.objects.create(
                        analysis=analysis,
                        model_id=rec["model_id"],
                        model_name=rec["model_name"],
                        provider=rec["provider"],
                        score=rec["score"],
                        rank=rec["rank"],
                        reasoning=rec["reasoning"],
                        tradeoffs=rec.get("tradeoffs", {}),
                        estimated_cost_per_message=float(rec.get("estimated_cost_per_message", 0)),
                        estimated_quality_score=rec.get("score", 0),
                    )

                # Serialize updated analysis
                analysis_serializer = ConversationAnalysisSerializer(analysis)

                return Response(
                    {"analysis": analysis_serializer.data},
                    status=status.HTTP_200_OK,
                )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

        except ContextLimitExceededException as e:
            logger.error(f"Context limit exceeded: {e}")
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except ValueError as e:
            logger.error(f"AI analysis validation error: {e}")
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        except Exception as e:
            logger.error(f"Error generating AI analysis: {e}", exc_info=True)
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def generate_analysis_stream(self, request, pk=None):
        """
        Generate AI-powered analysis with real-time progress updates.

        POST /api/consigliere/<session_id>/generate_analysis_stream/
        {
            "current_model": "anthropic/claude-3-opus"
        }

        Returns:
            Streaming NDJSON response with progress events:
            {"event": "progress", "data": {"step": "preparing_context", "status": "in_progress", ...}}
            {"event": "progress", "data": {"step": "calling_ai", "status": "in_progress", ...}}
            {"event": "complete", "data": {"analysis": {...}}}
            {"event": "error", "data": {"error": "...", "detail": "..."}}
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)

            if not hasattr(session, "analysis"):
                return Response(
                    {"error": "No analysis record found for this session"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            current_model = request.data.get("current_model")
            if not current_model:
                return Response(
                    {"error": "current_model is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            def event_stream():
                """Generator that yields NDJSON progress events"""
                progress_events = []

                def progress_callback_fn(event_data):
                    """Callback function that collects progress events"""
                    progress_events.append(event_data)
                    # Yield progress event
                    event = {
                        "event": "progress",
                        "data": event_data
                    }
                    return json.dumps(event) + "\n"

                try:
                    with transaction.atomic():
                        analysis = session.analysis

                        # Get basic metrics
                        metrics = {
                            "total_messages": analysis.total_messages,
                            "total_cost": analysis.total_cost,
                            "avg_latency": analysis.avg_latency,
                            "total_tokens": analysis.total_tokens,
                        }

                        # Create progress callback
                        progress_callback = ProgressCallback(progress_callback_fn)

                        # Send initial progress events as they come
                        for event_json in _generate_analysis_with_progress(
                            session, current_model, metrics, progress_callback, user=request.user
                        ):
                            yield event_json

                except ContextLimitExceededException as e:
                    logger.error(f"Context limit exceeded: {e}")
                    error_event = {
                        "event": "error",
                        "data": {
                            "error": get_user_friendly_error(e)
                        }
                    }
                    yield json.dumps(error_event, cls=DecimalEncoder) + "\n"

                except ValueError as e:
                    logger.error(f"AI analysis validation error: {e}")
                    error_event = {
                        "event": "error",
                        "data": {
                            "error": get_user_friendly_error(e)
                        }
                    }
                    yield json.dumps(error_event) + "\n"

                except Exception as e:
                    logger.error(f"Error generating AI analysis: {e}", exc_info=True)
                    error_event = {
                        "event": "error",
                        "data": {
                            "error": get_user_friendly_error(e)
                        }
                    }
                    yield json.dumps(error_event) + "\n"

            return StreamingHttpResponse(
                event_stream(),
                content_type="application/x-ndjson",
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                }
            )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["post"])
    def chat(self, request):
        """
        Send a message to Consigliere and get a response.

        POST /api/consigliere/chat/
        {
            "session_id": "uuid",
            "message": "What model should I use?",
            "current_model": "anthropic/claude-3-opus",
            "stream": false
        }

        Returns:
            {
                "message": { ... },
                "session_id": "uuid"
            }
        """
        serializer = ChatMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session_id = data["session_id"]
        user_message = data["message"]
        current_model = data["current_model"]
        stream = data.get("stream", False)
        parameters = data.get("parameters", {})

        try:
            # Get session
            session = ConsiglierSession.objects.get(
                id=session_id, user=request.user
            )

            # Save user message
            user_msg = ConsigliereMessage.objects.create(
                session=session, role="user", content=user_message
            )

            # Build context from session data
            context_builder = ContextBuilder()

            # Get analysis if available
            analysis_data = None
            if hasattr(session, "analysis"):
                analysis_serializer = ConversationAnalysisSerializer(session.analysis)
                analysis_data = analysis_serializer.data

            context = context_builder.build_context(
                chat_group=session.chat_group_data,
                analysis=analysis_data,
                user_preferences=analysis_data.get("user_preferences") if analysis_data else None,
            )

            # Get conversation history
            previous_messages = (
                session.messages.exclude(id=user_msg.id)
                .order_by("created_at")
                .values("role", "content")
            )

            messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in previous_messages
            ]
            messages.append({"role": "user", "content": user_message})

            # Generate Consigliere response
            chat_handler = ConsiglierChatHandler(current_model, user=request.user)

            if stream:
                # TODO: Implement streaming response
                # For now, fall back to non-streaming
                logger.warning("Streaming not yet implemented, using regular response")

            # Extract parameters with defaults
            response = chat_handler.chat(
                messages=messages,
                context=context,
                temperature=parameters.get("temperature", 0.7),
                max_tokens=parameters.get("max_tokens", 1000),
                top_p=parameters.get("top_p", 1.0),
                top_k=parameters.get("top_k", 0),
                frequency_penalty=parameters.get("frequency_penalty", 0.0),
                presence_penalty=parameters.get("presence_penalty", 0.0),
                repetition_penalty=parameters.get("repetition_penalty", 1.0),
                min_p=parameters.get("min_p", 0.0),
                top_a=parameters.get("top_a", 0.0),
                stream=stream,
            )

            # Save assistant message
            assistant_msg = ConsigliereMessage.objects.create(
                session=session,
                role="assistant",
                content=response["content"],
                model_used=response["model_used"],
                tokens_used=response["tokens_used"],
                prompt_tokens=response.get("prompt_tokens"),
                completion_tokens=response.get("completion_tokens"),
                cost=response["cost"],
                prompt_cost=response.get("prompt_cost"),
                completion_cost=response.get("completion_cost"),
                latency=response["latency"],
            )

            # Serialize response
            from .serializers import ConsigliereMessageSerializer

            msg_serializer = ConsigliereMessageSerializer(assistant_msg)

            return Response(
                {"message": msg_serializer.data, "session_id": session.id},
                status=status.HTTP_200_OK,
            )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            logger.error(f"Error in Consigliere chat: {e}", exc_info=True)
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["post"])
    def chat_stream(self, request):
        """
        Send a message to Consigliere and get a streaming response.

        POST /api/consigliere/chat_stream/
        {
            "session_id": "uuid",
            "message": "What model should I use?",
            "current_model": "anthropic/claude-3-opus",
            "stream": true,
            "parameters": { ... }
        }

        Returns:
            StreamingHttpResponse with Server-Sent Events:
            event: content
            data: {"content": "chunk..."}

            event: done
            data: {"usage": {...}, "cost": 0.001, "message_id": "uuid", ...}

            event: error
            data: {"error": "message"}
        """
        serializer = ChatMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session_id = data["session_id"]
        user_message = data["message"]
        current_model = data["current_model"]
        parameters = data.get("parameters", {})

        try:
            # Get session
            session = ConsiglierSession.objects.get(
                id=session_id, user=request.user
            )

            # Save user message
            user_msg = ConsigliereMessage.objects.create(
                session=session, role="user", content=user_message
            )

            # Build context from session data
            context_builder = ContextBuilder()

            # Get analysis if available
            analysis_data = None
            if hasattr(session, "analysis"):
                analysis_serializer = ConversationAnalysisSerializer(session.analysis)
                analysis_data = analysis_serializer.data

            context = context_builder.build_context(
                chat_group=session.chat_group_data,
                analysis=analysis_data,
                user_preferences=analysis_data.get("user_preferences") if analysis_data else None,
            )

            # Get conversation history
            previous_messages = (
                session.messages.exclude(id=user_msg.id)
                .order_by("created_at")
                .values("role", "content")
            )

            messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in previous_messages
            ]
            messages.append({"role": "user", "content": user_message})

            # Streaming response generator
            def event_stream():
                """Generator that yields SSE-formatted events"""
                chat_handler = ConsiglierChatHandler(current_model, user=request.user)

                try:
                    for chunk in chat_handler.chat_stream(
                        messages=messages,
                        context=context,
                        temperature=parameters.get("temperature", 0.7),
                        max_tokens=parameters.get("max_tokens", 1000),
                        top_p=parameters.get("top_p", 1.0),
                        top_k=parameters.get("top_k", 0),
                        frequency_penalty=parameters.get("frequency_penalty", 0.0),
                        presence_penalty=parameters.get("presence_penalty", 0.0),
                        repetition_penalty=parameters.get("repetition_penalty", 1.0),
                        min_p=parameters.get("min_p", 0.0),
                        top_a=parameters.get("top_a", 0.0),
                    ):
                        event_type = chunk.get("event")
                        event_data = chunk.get("data", {})

                        if event_type == "content":
                            # Yield content chunk
                            yield f"event: content\ndata: {json.dumps(event_data, cls=DecimalEncoder)}\n\n"

                        elif event_type == "done":

                            # Save assistant message to database
                            usage = event_data.get("usage", {})
                            assistant_msg = ConsigliereMessage.objects.create(
                                session=session,
                                role="assistant",
                                content=event_data.get("content", ""),
                                model_used=event_data.get("model", current_model),
                                tokens_used=usage.get("total_tokens", 0),
                                prompt_tokens=usage.get("prompt_tokens", 0),
                                completion_tokens=usage.get("completion_tokens", 0),
                                cost=event_data.get("cost"),
                                prompt_cost=event_data.get("prompt_cost"),
                                completion_cost=event_data.get("completion_cost"),
                                latency=event_data.get("latency"),
                            )

                            # Add message_id to response
                            done_data = {**event_data, "message_id": str(assistant_msg.id)}
                            yield f"event: done\ndata: {json.dumps(done_data, cls=DecimalEncoder)}\n\n"

                        elif event_type == "error":
                            # Yield error event
                            yield f"event: error\ndata: {json.dumps(event_data, cls=DecimalEncoder)}\n\n"

                except Exception as e:
                    logger.error(f"Error in streaming response: {e}", exc_info=True)
                    error_data = {"error": get_user_friendly_error(e)}
                    yield f"event: error\ndata: {json.dumps(error_data, cls=DecimalEncoder)}\n\n"

            return StreamingHttpResponse(
                event_stream(),
                content_type="text/event-stream",
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                }
            )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

        except Exception as e:
            logger.error(f"Error in Consigliere chat stream: {e}", exc_info=True)
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"])
    def retry_last(self, request, pk=None):
        """
        Delete the last assistant message and its preceding user message, to support Retry.

        POST /api/consigliere/<session_id>/retry_last/
        Returns:
            {
              "deleted_assistant_id": "uuid",
              "deleted_user_id": "uuid",
              "user_content": "..."
            }
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)

            with transaction.atomic():
                last_assistant = (
                    session.messages.filter(role="assistant").order_by("-created_at").first()
                )
                if not last_assistant:
                    return Response(
                        {"error": "No assistant message to retry"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # Find the closest preceding user message
                prev_user = (
                    session.messages.filter(role="user", created_at__lt=last_assistant.created_at)
                    .order_by("-created_at")
                    .first()
                )
                if not prev_user:
                    return Response(
                        {"error": "No preceding user message found for retry"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                user_content = prev_user.content
                deleted_assistant_id = str(last_assistant.id)
                deleted_user_id = str(prev_user.id)

                # Delete both messages
                prev_user.delete()
                last_assistant.delete()

                return Response(
                    {
                        "deleted_assistant_id": deleted_assistant_id,
                        "deleted_user_id": deleted_user_id,
                        "user_content": user_content,
                    },
                    status=status.HTTP_200_OK,
                )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error retrying last message: {e}", exc_info=True)
            return Response(
                {"error": get_user_friendly_error(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["get"])
    def recommendations(self, request, pk=None):
        """
        Get recommendations for a session.

        GET /api/consigliere/<session_id>/recommendations/

        Returns:
            {
                "recommendations": [ ... ]
            }
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)

            if not hasattr(session, "analysis"):
                return Response(
                    {"error": "No analysis available for this session"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            analysis_serializer = ConversationAnalysisSerializer(session.analysis)

            return Response(
                {"recommendations": analysis_serializer.data["recommendations"]},
                status=status.HTTP_200_OK,
            )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=["get"])
    def sessions(self, request):
        """
        List user's Consigliere sessions.

        GET /api/consigliere/sessions/

        Returns:
            {
                "sessions": [ ... ]
            }
        """
        sessions = ConsiglierSession.objects.filter(user=request.user).order_by(
            "-created_at"
        )[:20]  # Limit to 20 most recent

        serializer = ConsiglierSessionSummarySerializer(sessions, many=True)

        return Response({"sessions": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def session(self, request, pk=None):
        """
        Get full session details.

        GET /api/consigliere/<session_id>/session/

        Returns:
            Full session with messages and analysis
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)
            serializer = ConsiglierSessionSerializer(session)

            return Response(serializer.data, status=status.HTTP_200_OK)

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["post"])
    def continue_session(self, request, pk=None):
        """
        Continue a previous session with updated conversation data.

        POST /api/consigliere/<session_id>/continue/
        {
            "chat_group": { ... }  // Optional updated ChatGroup
        }

        Returns:
            Updated session data
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)

            serializer = ContinueSessionRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            # Update chat_group_data if provided
            if data.get("chat_group"):
                session.chat_group_data = data["chat_group"]
                session.save()

            # Reactivate session
            session.is_active = True
            session.save()

            response_serializer = ConsiglierSessionSerializer(session)

            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["post"])
    def clear_messages(self, request, pk=None):
        """
        Clear all messages from a Consigliere session.

        POST /api/consigliere/<session_id>/clear_messages/

        Returns:
            { "status": "success", "deleted_count": N }
        """
        try:
            session = ConsiglierSession.objects.get(pk=pk, user=request.user)

            # Delete all messages for this session
            deleted_count, _ = ConsigliereMessage.objects.filter(session=session).delete()

            return Response(
                {
                    "status": "success",
                    "deleted_count": deleted_count,
                },
                status=status.HTTP_200_OK,
            )

        except ConsiglierSession.DoesNotExist:
            return Response(
                {"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND
            )


def _generate_analysis_with_progress(session, current_model, metrics, progress_callback, user=None):
    """
    Helper function to generate analysis with progress updates.

    Yields NDJSON events as they happen in real-time (no buffering).

    Args:
        session: ConsiglierSession instance
        current_model: Model ID to use for analysis
        metrics: Pre-calculated metrics dict
        progress_callback: ProgressCallback (ignored, kept for compatibility)
        user: User instance for API key resolution
    """
    # Create AI analyzer
    ai_analyzer = AIAnalyzer(current_model, user=user)

    # Iterate over streaming analysis generator
    ai_result = None
    for event in ai_analyzer.analyze_with_ai_streaming(
        chat_group_data=session.chat_group_data,
        current_model_id=current_model,
        metrics=metrics,
    ):
        # Check if this is the final result
        if "_result" in event:
            ai_result = event["_result"]
            break

        # Otherwise, it's a progress event - yield immediately
        progress_event = {
            "event": "progress",
            "data": event
        }
        yield json.dumps(progress_event, cls=DecimalEncoder) + "\n"

    # Process final result
    if ai_result is None:
        error_event = {
            "event": "error",
            "data": {
                "error": "No result received from AI analysis",
                "detail": "Analysis generator did not yield a result"
            }
        }
        yield json.dumps(error_event, cls=DecimalEncoder) + "\n"
        return

    # Update analysis record
    analysis = session.analysis
    analysis.conversation_type = ai_result["conversation_type"]
    analysis.detected_needs = ai_result["detected_needs"]
    analysis.insights = ai_result["insights"]
    analysis.recommended_model_from_conversation = ai_result.get("recommended_from_conversation", {})
    analysis.save()

    # Delete old recommendations and create new ones
    analysis.recommendations.all().delete()

    # Create alternative models from AI (convert Decimal to float)
    for rec in ai_result.get("alternative_models", []):
        ModelRecommendation.objects.create(
            analysis=analysis,
            model_id=rec["model_id"],
            model_name=rec["model_name"],
            provider=rec["provider"],
            score=rec["score"],
            rank=rec["rank"],
            reasoning=rec["reasoning"],
            tradeoffs=rec.get("tradeoffs", {}),
            estimated_cost_per_message=float(rec.get("estimated_cost_per_message", 0)),
            estimated_quality_score=rec.get("score", 0),
        )

    # Serialize updated analysis
    from .serializers import ConversationAnalysisSerializer
    analysis_serializer = ConversationAnalysisSerializer(analysis)

    # Yield completion event
    complete_event = {
        "event": "complete",
        "data": {
            "analysis": analysis_serializer.data
        }
    }
    yield json.dumps(complete_event, cls=DecimalEncoder) + "\n"
