"""
Agent-core streaming (V2) endpoint.
"""

import json
import logging

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.http import StreamingHttpResponse

from ..catalog_service import CatalogService
from ..rate_limiter import RateLimiter
from ..services.user_instructions_service import get_user_instructions, get_chat_instructions

logger = logging.getLogger(__name__)


# ===========================
# Agent-core Streaming (V2)
# ===========================


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_complete_langchain(request):
    """
    Stream completion with automatic tool calling, on the agent core.

    This is the V2 endpoint that properly handles multiple tool call cycles.
    """
    from ..uploaded_files_helper import encode_uploaded_files, prepare_uploaded_files_context

    # Handle both JSON and FormData (multipart/form-data with files)
    if request.content_type and 'multipart/form-data' in request.content_type:
        # FormData: fields are in request.POST, need to parse JSON strings
        data = request.POST.dict()

        # Parse messages from JSON string
        messages_json = data.get("messages", "[]")
        try:
            messages = json.loads(messages_json) if isinstance(messages_json, str) else messages_json
        except json.JSONDecodeError:
            messages = []

        # Parse other parameters
        model = data.get("model")
        temperature = float(data.get("temperature", 0.7))
        max_tokens = int(data.get("max_tokens", 1000))

        # Feature flags - parse booleans from strings
        enable_brave_search = data.get("enable_brave_search", "false").lower() == "true"
        enable_google_maps = enable_brave_search  # Auto-enabled with Extended Search
        enable_image_generation = data.get("enable_image_generation", "false").lower() == "true"
        enable_video_generation = data.get("enable_video_generation", "false").lower() == "true"
        enable_reasoning = data.get("enable_reasoning", "false").lower() == "true"
        enable_file_tools = data.get("enable_file_tools", "false").lower() == "true"
        enable_mcp_tools = data.get("enable_mcp_tools", "false").lower() == "true"
        enable_voice_mode = data.get("enable_voice_mode", "false").lower() == "true"
        enable_sparks = data.get("enable_sparks", "false").lower() == "true"
        enable_knowledge_base = data.get("enable_knowledge_base", "false").lower() == "true"

        # Spark auto-fix request (JSON string in form data)
        spark_fix_request_str = data.get("spark_fix_request")
        spark_fix_request = None
        if spark_fix_request_str:
            try:
                spark_fix_request = json.loads(spark_fix_request_str)
                logger.info(f"[LangChain] Spark fix request for spark_id={spark_fix_request.get('spark_id')}")
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[LangChain] Invalid spark_fix_request JSON: {spark_fix_request_str}")

        spark_ignite_request_str = data.get("spark_ignite_request")
        spark_ignite_request = None
        if spark_ignite_request_str:
            try:
                spark_ignite_request = json.loads(spark_ignite_request_str)
                # Enrich with spark code from DB (frontend only sends spark_id + title)
                from sparks.models import Spark
                try:
                    spark = Spark.objects.get(id=spark_ignite_request["spark_id"])
                    spark_ignite_request["spark_code"] = spark.get_code()
                    spark_ignite_request["dependencies"] = json.dumps(spark.dependencies or [])
                    logger.info(f"[LangChain] Spark ignite request for spark_id={spark_ignite_request.get('spark_id')}")
                except Spark.DoesNotExist:
                    logger.warning(f"[LangChain] Spark not found for ignite: {spark_ignite_request.get('spark_id')}")
                    spark_ignite_request = None
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"[LangChain] Invalid spark_ignite_request JSON: {spark_ignite_request_str}")

        conversation_id = data.get("conversation_id", "default")
        chat_id = data.get("chat_id")

        # Additional parameters
        system_prompt = data.get("system_prompt")
        message_id = data.get("message_id")
        reasoning_effort = data.get("reasoning_effort")
        reasoning_max_tokens = int(data.get("reasoning_max_tokens")) if data.get("reasoning_max_tokens") else None
    else:
        # JSON: use request.data directly
        data = request.data
        model = data.get("model")
        messages = data.get("messages", [])
        temperature = data.get("temperature", 0.7)
        max_tokens = data.get("max_tokens", 1000)

        enable_brave_search = data.get("enable_brave_search", False)
        enable_google_maps = enable_brave_search  # Auto-enabled with Extended Search
        enable_image_generation = data.get("enable_image_generation", False)
        enable_video_generation = data.get("enable_video_generation", False)
        enable_reasoning = data.get("enable_reasoning", False)
        enable_file_tools = data.get("enable_file_tools", False)
        enable_mcp_tools = data.get("enable_mcp_tools", False)
        enable_voice_mode = data.get("enable_voice_mode", False)
        enable_sparks = data.get("enable_sparks", False)
        enable_knowledge_base = data.get("enable_knowledge_base", False)

        # Spark auto-fix request
        spark_fix_request = data.get("spark_fix_request")
        if spark_fix_request:
            logger.info(f"[LangChain] Spark fix request for spark_id={spark_fix_request.get('spark_id')}")

        # Spark ignite request
        spark_ignite_request = data.get("spark_ignite_request")
        if spark_ignite_request:
            # Enrich with spark code from DB (frontend only sends spark_id + title)
            from sparks.models import Spark
            try:
                spark = Spark.objects.get(id=spark_ignite_request["spark_id"])
                spark_ignite_request["spark_code"] = spark.get_code()
                spark_ignite_request["dependencies"] = json.dumps(spark.dependencies or [])
                logger.info(f"[LangChain] Spark ignite request for spark_id={spark_ignite_request.get('spark_id')}")
            except Spark.DoesNotExist:
                logger.warning(f"[LangChain] Spark not found for ignite: {spark_ignite_request.get('spark_id')}")
                spark_ignite_request = None

        conversation_id = data.get("conversation_id", "default")
        chat_id = data.get("chat_id")

        # Additional parameters
        system_prompt = data.get("system_prompt")
        message_id = data.get("message_id")
        reasoning_effort = data.get("reasoning_effort")
        reasoning_max_tokens = data.get("reasoning_max_tokens")

    # Parse sterna_strength for "regenerate stronger"
    sterna_strength = data.get("sterna_strength") if isinstance(data, dict) else None

    logger.info(f"[LangChain] Stream request received for model: {model}")
    logger.info(f"[LangChain] Voice mode enabled: {enable_voice_mode}")

    # --- Sterna intelligent routing intercept ---
    sterna_resolution = None
    if model:
        from llm.smart_router.router import SmartRouter
        if SmartRouter.is_auto_router_model(model):
            router = SmartRouter()
            min_score_override = 70 if sterna_strength == "strong" else None
            sterna_resolution = router.resolve(
                model_id=model,
                messages=messages,
                conversation_id=conversation_id,
                user=request.user,
                min_score_override=min_score_override,
            )
            model = sterna_resolution.resolved_model_id
            logger.info(
                f"[Sterna] Resolved -> {model} "
                f"(tier={sterna_resolution.tier}, score={sterna_resolution.final_score})"
            )

    # Filter out any None messages (defensive - frontend should not send them)
    if messages:
        original_count = len(messages)
        messages = [m for m in messages if m is not None]
        if len(messages) != original_count:
            logger.warning(f"[LangChain] Filtered out {original_count - len(messages)} None message(s)")

    # Check rate limiting
    rate_limiter = RateLimiter()

    # Handle uploaded files
    uploaded_files_encoded = []
    files_context_message = None

    # First, check if there are already files in the attachments folder (from previous messages)
    # This ensures the model always knows about uploaded files throughout the conversation
    if enable_file_tools and chat_id:
        import httpx
        import asyncio

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        auth_token_check = auth_header[7:] if auth_header.startswith('Bearer ') else None
        orchestrator_url = "http://orchestrator:8003"

        async def check_existing_files():
            """Check if attachments folder has files from previous messages"""
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f"{orchestrator_url}/fs/list",
                        json={
                            "path": "attachments",
                            "user_id": str(request.user.id),
                            "conversation_id": conversation_id,
                            "chat_id": chat_id,
                            "sync_mode": True
                        },
                        headers={"Authorization": f"Bearer {auth_token_check}"}
                    )
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success") and result.get("files"):
                            existing_files = [f["name"] for f in result["files"] if f["type"] == "file"]
                            if existing_files:
                                return existing_files
            except Exception as e:
                logger.debug(f"[LangChain] Could not check existing attachments: {e}")
            return []

        # Run async check
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            existing_files = loop.run_until_complete(check_existing_files())
            if existing_files:
                files_list = ", ".join(existing_files)
                attachments_dir = f"/workspace/chat-{chat_id}/attachments"
                files_context_message = f"""📎 Uploaded files available ({len(existing_files)}): {files_list}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{existing_files[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""
                logger.info(f"[LangChain] Found {len(existing_files)} existing file(s) in attachments folder")
        finally:
            loop.close()

    # Check for files in the request (multipart/form-data)
    if request.FILES:
        attachments = list(request.FILES.values())
        logger.info(f"[LangChain] Found {len(attachments)} uploaded file(s)")

        # Encode files for transmission to orchestrator
        uploaded_files_encoded = encode_uploaded_files(attachments)

        # Generate context message to inform the model (pass chat_id for folder path)
        files_context_message = prepare_uploaded_files_context(attachments, chat_id=chat_id)

        logger.info(f"[LangChain] Encoded {len(uploaded_files_encoded)} file(s) for workspace")

        # Copy files to workspace IMMEDIATELY (so they're available for all subsequent messages)
        if enable_file_tools and uploaded_files_encoded:
            import httpx
            import asyncio

            # Extract JWT token for orchestrator auth
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            auth_token_temp = auth_header[7:] if auth_header.startswith('Bearer ') else None

            orchestrator_url = "http://orchestrator:8003"

            async def copy_files_to_workspace():
                """Copy uploaded files to attachments folder immediately"""
                async with httpx.AsyncClient(timeout=30.0) as client:
                    for file_data in uploaded_files_encoded:
                        try:
                            # Files go to attachments/ folder inside the chat workspace
                            attachments_path = f"attachments/{file_data['filename']}"

                            response = await client.post(
                                f"{orchestrator_url}/fs/write",
                                json={
                                    "path": attachments_path,  # Store in attachments subfolder
                                    "content": file_data["content_base64"],  # Will be decoded by orchestrator
                                    "user_id": str(request.user.id),
                                    "conversation_id": conversation_id,
                                    "chat_id": chat_id,
                                    "sync_mode": True,
                                    "is_base64": True  # Flag to tell orchestrator to decode
                                },
                                headers={"Authorization": f"Bearer {auth_token_temp}"}
                            )
                            if response.status_code == 200:
                                logger.info(f"[LangChain] Copied uploaded file to attachments: {attachments_path}")
                            else:
                                logger.error(f"[LangChain] Failed to copy file {file_data['filename']}: {response.status_code}")
                        except Exception as e:
                            logger.error(f"[LangChain] Error copying file {file_data['filename']}: {e}")

            # Run the async copy operation
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(copy_files_to_workspace())
            finally:
                loop.close()

    # Also check for files in data (if sent as JSON with base64)
    elif data.get("uploaded_files"):
        uploaded_files_encoded = data.get("uploaded_files")
        # Extract filenames for context
        filenames = [f.get("filename") for f in uploaded_files_encoded if f.get("filename")]
        if filenames:
            files_list = ", ".join(filenames)
            attachments_dir = f"/workspace/chat-{chat_id}/attachments"
            files_context_message = f"""📎 Uploaded files available ({len(filenames)}): {files_list}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{filenames[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""
            logger.info(f"[LangChain] Received {len(uploaded_files_encoded)} pre-encoded file(s)")

    # Handle asset-backed files (persisted in R2, sent as asset IDs by frontend)
    # This covers the case where File objects aren't available (page reload, pre-upload)
    workspace_assets_raw = data.get("workspace_assets", [])
    logger.info(f"[LangChain] workspace_assets_raw={workspace_assets_raw}, enable_file_tools={enable_file_tools}, chat_id={chat_id}")
    if isinstance(workspace_assets_raw, str):
        try:
            workspace_assets_raw = json.loads(workspace_assets_raw)
        except (json.JSONDecodeError, ValueError):
            workspace_assets_raw = []

    MAX_ASSET_SIZE = 25 * 1024 * 1024  # 25MB limit per file

    if workspace_assets_raw and enable_file_tools and chat_id:
        import base64
        import uuid as uuid_mod
        import httpx
        import asyncio
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service

        # Validate asset IDs as UUIDs
        valid_asset_ids = []
        asset_filename_map = {}
        for wa in workspace_assets_raw:
            aid = wa.get("asset_id", "")
            try:
                uuid_mod.UUID(str(aid))
                valid_asset_ids.append(str(aid))
                asset_filename_map[str(aid)] = wa.get("filename", "unknown")
            except (ValueError, AttributeError):
                logger.warning(f"[LangChain] Invalid asset ID in workspace_assets: {aid}")

        if valid_asset_ids:
            storage = get_asset_storage_service()
            assets = Asset.objects.filter(id__in=valid_asset_ids, user=request.user)
            assets_map = {str(a.id): a for a in assets}

            auth_header_assets = request.META.get('HTTP_AUTHORIZATION', '')
            auth_token_assets = auth_header_assets[7:] if auth_header_assets.startswith('Bearer ') else None
            orchestrator_url = "http://orchestrator:8003"

            # Pre-download asset content from R2 (sync ORM/storage, before async loop)
            asset_payloads = []  # list of (filename, content_b64, path)
            for aid in valid_asset_ids:
                asset = assets_map.get(aid)
                if not asset:
                    logger.warning(f"[LangChain] Asset {aid} not found or not owned by user")
                    continue
                if asset.size_bytes and asset.size_bytes > MAX_ASSET_SIZE:
                    logger.warning(f"[LangChain] Asset {asset.filename} too large ({asset.size_bytes} bytes), skipping workspace copy")
                    continue
                content_bytes = storage.retrieve_asset(asset)
                if not content_bytes:
                    logger.warning(f"[LangChain] Could not retrieve asset {aid}")
                    continue
                filename = asset_filename_map.get(aid, asset.filename)
                content_b64 = base64.b64encode(content_bytes).decode('utf-8')
                path = f"attachments/{filename}"
                asset_payloads.append((filename, content_b64, path))

            asset_copied_filenames = []

            if asset_payloads:
                async def copy_assets_to_workspace():
                    """Copy asset files to sandbox attachments folder"""
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        for filename, content_b64, path in asset_payloads:
                            try:
                                response = await client.post(
                                    f"{orchestrator_url}/fs/write",
                                    json={
                                        "path": path,
                                        "content": content_b64,
                                        "user_id": str(request.user.id),
                                        "conversation_id": conversation_id,
                                        "chat_id": chat_id,
                                        "sync_mode": True,
                                        "is_base64": True,
                                    },
                                    headers={"Authorization": f"Bearer {auth_token_assets}"},
                                )
                                if response.status_code == 200:
                                    asset_copied_filenames.append(filename)
                                    logger.info(f"[LangChain] Copied asset to workspace: {path}")
                                else:
                                    logger.error(f"[LangChain] Failed to copy asset {filename}: {response.status_code}")
                            except Exception as e:
                                logger.error(f"[LangChain] Error copying asset {filename}: {e}")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(copy_assets_to_workspace())
                finally:
                    loop.close()

            # Merge copied asset filenames into context message
            if asset_copied_filenames:
                attachments_dir = f"/workspace/chat-{chat_id}/attachments"
                if files_context_message:
                    # Append to existing context (from request.FILES or check_existing_files)
                    files_context_message += f"\n\nAdditional files from attachments: {', '.join(asset_copied_filenames)} (in `{attachments_dir}/`)"
                else:
                    files_context_message = f"""📎 Uploaded files available ({len(asset_copied_filenames)}): {', '.join(asset_copied_filenames)}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{asset_copied_filenames[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""
                logger.info(f"[LangChain] Copied {len(asset_copied_filenames)} asset(s) to workspace")

    # Enrich the last user message with files context if needed
    if files_context_message and messages and enable_file_tools:
        # Find the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                # Prepend the files context to the user message
                original_content = messages[i].get("content", "")
                messages[i]["content"] = f"{files_context_message}\n\n{original_content}"
                logger.info("[LangChain] Enriched user message with files context")
                break

    # Extract JWT token
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    auth_token = auth_header[7:] if auth_header.startswith('Bearer ') else None

    # API key + endpoint are resolved below (after the model-capability
    # check) via resolve_endpoint, so provider-scoped BYOK keys can route
    # eligible chat models directly to the provider.

    # Use wait_if_needed for rate limiting (like the other endpoints)
    project_id = str(data.get("project_id")) if data.get("project_id") else None
    try:
        rate_limiter.wait_if_needed(model, project_id=project_id, max_wait=10.0)
    except Exception as e:
        logger.error(f"[LangChain] Rate limit error: {e}")
        error_response = {
            "error": "Too many requests. Please wait a moment and try again."
        }
        return StreamingHttpResponse(
            iter([f"event: error\ndata: {json.dumps(error_response)}\n\n"]),
            content_type='text/event-stream'
        )

    # Check model capabilities BEFORE creating agent
    # If model doesn't support function calling, disable all tool-related features
    model_obj = None
    supports_functions = True  # Default to True if catalog lookup fails
    output_modalities = ["text"]  # Default to text only
    try:
        catalog = CatalogService()
        model_obj = catalog.get_model(model)
        if model_obj:
            supports_functions = model_obj.get("supports_functions", True)
            output_modalities = model_obj.get("output_modalities", ["text"])
            if not supports_functions:
                # Model doesn't support function calling - disable all tool features
                if enable_file_tools or enable_brave_search or enable_google_maps or enable_mcp_tools:
                    logger.warning(f"[LangChain] Model {model} does not support function calling. Disabling tools (file_tools={enable_file_tools}, brave_search={enable_brave_search}, google_maps={enable_google_maps}, mcp_tools={enable_mcp_tools})")
                    enable_file_tools = False
                    enable_brave_search = False
                    enable_google_maps = False
                    enable_mcp_tools = False
            # Log if model supports image generation
            if "image" in output_modalities:
                logger.info(f"[LangChain] Model {model} supports image generation (output_modalities: {output_modalities})")
    except Exception as e:
        logger.warning(f"[LangChain] Failed to check model capabilities: {e}")

    # Resolve max_tokens using model limits from the catalog
    # The max_tokens parameter is for OUTPUT tokens, not total context
    FALLBACK_MAX_OUTPUT_TOKENS = 16384  # Fallback when model info unavailable
    if model_obj:
        model_context_length = model_obj.get("max_tokens") or 128000
        model_max_completion = model_obj.get("max_completion_tokens")
        if model_max_completion:
            # Model has explicit max completion tokens - use it
            max_tokens = model_max_completion
        else:
            # No explicit limit - use half the context as a safe ceiling
            max_tokens = model_context_length // 2
        logger.info(f"[LangChain] Using model max_tokens={max_tokens} (model_max_completion={model_max_completion}, context={model_context_length})")
    else:
        max_tokens = max(max_tokens, FALLBACK_MAX_OUTPUT_TOKENS)
        logger.warning(f"[LangChain] No model info, using max_tokens={max_tokens}")

    # Load MCP tools if enabled
    mcp_tools_list = None
    mention_priority_prompt = None
    forced_tool_name = None
    media_tool_params = None
    if enable_mcp_tools:
        try:
            from mcp.registry import get_registry
            registry = get_registry()
            mcp_tools_list = registry.get_available_tools_sync(request.user)
            if mcp_tools_list:
                logger.info(f"[LangChain] Loaded {len(mcp_tools_list)} MCP tools for user {request.user.id}")

                # Parse @mentions from user messages and build priority prompt
                try:
                    from ..mention_parser import extract_mentions_from_messages, build_mention_priority_prompt, get_forced_tool_choice, extract_media_params
                    mentions = extract_mentions_from_messages(messages)
                    if mentions:
                        logger.info(f"[LangChain] Parsed {len(mentions)} @mention(s): {[m.full_name for m in mentions]}")
                        # Debug: log available tools and their server names
                        available_servers = set()
                        for tool in mcp_tools_list:
                            server = getattr(tool, 'server', None)
                            if server:
                                available_servers.add(server.name)
                        logger.info(f"[LangChain] Available MCP servers: {list(available_servers)}")

                        # Check if user explicitly selected a coding agent tool (force it)
                        forced_tool_name = get_forced_tool_choice(mentions)
                        if forced_tool_name:
                            logger.info(f"[LangChain] Will force tool_choice for: {forced_tool_name}")

                        # Extract media tool params if force-calling a media tool
                        media_tool_params = None
                        if forced_tool_name in ('generate_image', 'generate_video', 'animate_image', 'upscale_video', 'animate_character'):
                            last_user_msg = next((m for m in reversed(messages) if m.get('role') == 'user'), None)
                            if last_user_msg:
                                content = last_user_msg.get('content', '')
                                if isinstance(content, list):
                                    content = ' '.join(p.get('text', '') for p in content if isinstance(p, dict))
                                media_tool_params = extract_media_params(content)
                                if media_tool_params:
                                    logger.info(f"[LangChain] Extracted media tool params: {media_tool_params}")

                        mention_priority_prompt = build_mention_priority_prompt(mentions, mcp_tools_list)
                        if mention_priority_prompt:
                            logger.info(f"[LangChain] Built mention priority prompt for {len(mentions)} mention(s)")
                        else:
                            logger.warning("[LangChain] Mentions parsed but no valid priority prompt built (server/tool not found)")
                except Exception as e:
                    logger.warning(f"[LangChain] Failed to parse @mentions: {e}", exc_info=True)
            else:
                logger.warning(f"[LangChain] MCP enabled but no tools found for user {request.user.id}")
        except Exception as e:
            logger.error(f"[LangChain] Failed to load MCP tools: {e}")

    logger.info(f"[LangChain] Creating agent: model={model}, max_tokens={max_tokens}, file_tools={enable_file_tools}, mcp_tools={enable_mcp_tools}, reasoning={enable_reasoning}, reasoning_effort={reasoning_effort}, reasoning_max_tokens={reasoning_max_tokens}")

    from llm.agent.model_metadata import build_model_metadata
    model_metadata = build_model_metadata(
        model_obj, file_tools_enabled=enable_file_tools, message_id=message_id
    )

    # Create agent (passes V2 params for tool discovery when enabled)
    model_display_name = model_obj.get("name") if model_obj else None

    # Fetch global user instructions from preferences service
    global_instructions = get_user_instructions(
        user_id=str(request.user.id),
        auth_token=auth_token or ""
    )

    # Fetch chat-specific instructions from database
    chat_instructions = get_chat_instructions(
        chat_id=chat_id,
        user_id=str(request.user.id)
    )

    # Build the custom prompt this turn is created with, combining the
    # global user instructions, the chat's own, the chat's custom prompt,
    # and any @mention priority instructions.
    from llm.agent.prompt_assembly import build_effective_system_prompt
    effective_system_prompt = build_effective_system_prompt(
        system_prompt=system_prompt,
        global_instructions=global_instructions,
        chat_instructions=chat_instructions,
        mention_priority_prompt=mention_priority_prompt,
    )

    # Resolve API key + endpoint for the chat model (provider-scoped BYOK).
    # Image-capable chat models always stay on OpenRouter (V1 scope), so
    # they resolve without a model_id.
    from llm.services.api_key_resolver import resolve_endpoint
    byok_model_id = model if "image" not in output_modalities else None
    try:
        api_key, chat_base_url, _chat_origin, chat_provider_slug = resolve_endpoint(
            user=request.user, model_id=byok_model_id,
        )
    except ValueError:
        # No key anywhere — preserve the previous failure mode (agent
        # construction fails downstream exactly as before).
        api_key, chat_base_url, chat_provider_slug = None, None, None

    # The turn itself runs on the agent core: see
    # llm.agent_service.endpoint for the request it builds and the
    # frames it speaks.
    from llm.agent.feature_flags import AgentFeatureFlags
    from llm.agent_service.endpoint import agent_core_streaming_response
    return agent_core_streaming_response(
        request=request,
        model=model,
        messages=messages,
        conversation_id=conversation_id,
        chat_id=chat_id,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=effective_system_prompt,
        api_key=api_key,
        base_url=chat_base_url,
        provider_slug=chat_provider_slug,
        flags=AgentFeatureFlags(
            file_tools=enable_file_tools,
            brave_search=enable_brave_search,
            google_maps=enable_google_maps,
            image_generation=enable_image_generation,
            video_generation=enable_video_generation,
            reasoning=enable_reasoning,
            mcp_tools=enable_mcp_tools,
            voice_mode=enable_voice_mode,
            sparks=enable_sparks,
            knowledge_base=enable_knowledge_base,
        ),
        auth_token=auth_token or "",
        model_display_name=model_display_name,
        model_metadata=model_metadata,
        uploaded_files=uploaded_files_encoded or None,
        sterna_resolution=sterna_resolution,
        media_tool_params=media_tool_params,
        spark_fix_request=spark_fix_request,
        spark_ignite_request=spark_ignite_request,
        forced_tool_name=forced_tool_name,
        reasoning_effort=reasoning_effort,
        reasoning_max_tokens=reasoning_max_tokens,
        output_modalities=output_modalities,
    )


