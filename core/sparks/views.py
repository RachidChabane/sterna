"""
API views for Spark management.
"""
import logging
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Prefetch
from django.http import HttpResponse

import httpx

from .models import Spark, SparkDeployment, App
from .serializers import (
    SparkSerializer,
    SparkListSerializer,
    SparkCreateSerializer,
    SparkUpdateSerializer,
    SparkDeploymentSerializer,
    AppSerializer,
    AppListSerializer,
)

logger = logging.getLogger(__name__)


class SparkPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 100


class SparkViewSet(viewsets.ModelViewSet):
    """
    API endpoints for Spark management.

    list: List all sparks for the authenticated user
    create: Create a new spark
    retrieve: Get a single spark with code
    update: Update a spark (creates new version)
    destroy: Delete a spark
    """
    permission_classes = [IsAuthenticated]
    pagination_class = SparkPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'framework']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']

    def get_queryset(self):
        """Filter sparks to only those owned by the current user.

        For list action, only return the latest version of each spark
        (i.e., sparks that don't have children).
        Supports ?framework= query param for filtering by type.
        """
        base_qs = Spark.objects.filter(user=self.request.user).prefetch_related(
            Prefetch(
                'deployments',
                queryset=SparkDeployment.objects.order_by('-created_at'),
            )
        )

        if self.action == 'list':
            # Exclude sparks that have a newer version (sparks that are parent of another spark)
            sparks_with_children = Spark.objects.filter(
                user=self.request.user,
                parent__isnull=False
            ).values_list('parent_id', flat=True)
            base_qs = base_qs.exclude(id__in=sparks_with_children)

            # Optional framework filter (supports comma-separated values)
            framework = self.request.query_params.get('framework')
            if framework:
                frameworks = [f.strip() for f in framework.split(',') if f.strip()]
                if len(frameworks) == 1:
                    base_qs = base_qs.filter(framework=frameworks[0])
                elif frameworks:
                    base_qs = base_qs.filter(framework__in=frameworks)

        return base_qs

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'list':
            return SparkListSerializer
        elif self.action == 'create':
            return SparkCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return SparkUpdateSerializer
        return SparkSerializer

    def perform_create(self, serializer):
        """Create a new spark."""
        from decimal import Decimal

        from usage_quota.billing.service import get_billing_service
        from usage_quota.models import FeatureType, ServiceType

        get_billing_service().check_quota(
            user=self.request.user,
            service=ServiceType.OPENROUTER,
            estimated_cost=Decimal('0'),
            feature=FeatureType.CHAT,
            feature_name='spark_generation',
        )
        spark = serializer.save()
        logger.info(f"Created spark {spark.id}: {spark.title}")

    def perform_destroy(self, instance):
        """Delete a spark and clean up generated R2 assets."""
        if instance.generated_r2_key:
            try:
                from workspaces.services.workspace_storage import WorkspaceStorageService
                storage = WorkspaceStorageService()
                storage._delete_from_r2(instance.generated_r2_key)
                logger.info(f"Deleted generated R2 asset for spark {instance.id}")
            except Exception as e:
                logger.warning(f"Failed to delete R2 asset for spark {instance.id}: {e}")
        instance.delete()

    def perform_update(self, serializer):
        """
        Update a spark by creating a new version.

        Instead of modifying the existing spark, we create a new one
        with incremented version and parent reference.
        """
        original = self.get_object()

        # Get update data
        title = serializer.validated_data.get('title', original.title)
        description = serializer.validated_data.get('description', original.description)
        code = serializer.validated_data.get('code')
        dependencies = serializer.validated_data.get('dependencies', original.dependencies)

        # Create new version
        new_spark = Spark(
            user=original.user,
            chat=original.chat,
            message=original.message,
            title=title,
            description=description,
            framework=original.framework,
            dependencies=dependencies,
            version=original.version + 1,
            parent=original,
        )

        # Save code
        if code:
            new_spark.save_code(code)
        else:
            # Copy code from original
            original_code = original.get_code()
            new_spark.save_code(original_code)

        new_spark.save()

        # Update serializer instance to return new spark
        serializer.instance = new_spark
        logger.info(f"Created spark version {new_spark.version} for {original.id}")

    @action(detail=True, methods=['get'])
    def code(self, request, pk=None):
        """
        Retrieve spark code directly.

        Returns the code as text/typescript for direct use.
        """
        spark = self.get_object()
        code = spark.get_code()

        return HttpResponse(
            code,
            content_type='text/typescript',
            headers={
                'Content-Disposition': f'inline; filename="{spark.title}.tsx"'
            }
        )

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """
        List all versions of a spark.

        Finds the root spark and traverses the version chain to return all versions.
        Returns versions sorted by version number descending (newest first).
        """
        spark = self.get_object()

        # Find root spark (the original without a parent)
        root = spark
        while root.parent:
            root = root.parent

        # Build the full version chain by traversing children
        # Start with root and follow the version chain
        all_versions = [root]
        current = root

        # Follow the chain through direct children
        while True:
            # Find child of current (there should be at most one direct child)
            child = Spark.objects.filter(parent=current, user=request.user).first()
            if child:
                all_versions.append(child)
                current = child
            else:
                break

        serializer = SparkListSerializer(all_versions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_chat(self, request):
        """
        List sparks for a specific chat.

        Query params:
            chat_id: UUID of the chat
        """
        chat_id = request.query_params.get('chat_id')
        if not chat_id:
            return Response(
                {'error': 'chat_id query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        sparks = self.get_queryset().filter(chat_id=chat_id)
        serializer = SparkListSerializer(sparks, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """
        Download spark content as a file.

        For CSV: serves code with UTF-8 BOM and text/csv content type
        For ICS: serves code with text/calendar content type
        For PDF/DOCX: redirects to presigned R2 URL (future)
        For renderable types: returns 404
        """
        spark = self.get_object()

        if spark.is_renderable():
            return Response(
                {'error': 'This spark type does not support download'},
                status=status.HTTP_404_NOT_FOUND
            )

        content = spark.get_code()
        filename = spark.get_sanitized_filename()
        mime_type = spark.get_mime_type()

        if spark.framework == 'csv':
            # Prepend UTF-8 BOM for Excel compatibility on Windows
            bom = '\xEF\xBB\xBF'
            response = HttpResponse(
                bom + content,
                content_type=f'{mime_type}; charset=utf-8',
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        if spark.framework == 'ics':
            response = HttpResponse(
                content,
                content_type=f'{mime_type}; charset=utf-8',
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        if spark.framework in ('pdf', 'docx', 'xlsx'):
            if spark.generated_r2_key:
                from workspaces.services.workspace_storage import WorkspaceStorageService
                storage = WorkspaceStorageService()
                try:
                    file_bytes = storage._download_from_r2(spark.generated_r2_key)
                    if file_bytes:
                        response = HttpResponse(
                            file_bytes,
                            content_type=mime_type,
                        )
                        response['Content-Disposition'] = f'inline; filename="{filename}"'
                        return response
                except Exception as e:
                    logger.warning(f"Failed to retrieve R2 file for spark {spark.id}: {e}")

            return Response(
                {'error': 'Generated document not yet available'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {'error': 'Unsupported framework for download'},
            status=status.HTTP_400_BAD_REQUEST
        )

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        """
        Duplicate a spark.

        Creates a new spark with "(Copy)" appended to the title.
        """
        original = self.get_object()

        # Create duplicate
        duplicate = Spark(
            user=request.user,
            title=f"{original.title} (Copy)",
            description=original.description,
            framework=original.framework,
            dependencies=original.dependencies.copy() if original.dependencies else [],
            version=1,
        )

        # Copy code
        duplicate.save_code(original.get_code())
        duplicate.save()

        serializer = SparkSerializer(duplicate, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def deployments(self, request, pk=None):
        """List all deployments for a spark."""
        spark = self.get_object()
        deps = SparkDeployment.objects.filter(spark=spark, user=request.user)
        serializer = SparkDeploymentSerializer(deps, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def deploy(self, request, pk=None):
        """Deploy spark's project to Vercel. No AI — just tar + upload."""
        import threading
        from decimal import Decimal

        from usage_quota.billing.service import get_billing_service
        from usage_quota.models import FeatureType, ServiceType

        get_billing_service().check_quota(
            user=request.user,
            service=ServiceType.OPENROUTER,
            estimated_cost=Decimal('0'),
            feature=FeatureType.OTHER,
            feature_name='spark_deploy',
        )

        spark = self.get_object()

        if spark.framework != 'react':
            return Response(
                {"error": "Only React sparks can be deployed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not spark.is_ignited:
            return Response(
                {"error": "Spark must be ignited first. Use Ignite to scaffold the project."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Dedup: check for active deployment
        active = SparkDeployment.objects.filter(
            spark=spark,
            user=request.user,
            status__in=['pending', 'deploying'],
        ).first()
        if active:
            return Response(
                SparkDeploymentSerializer(active).data,
                status=status.HTTP_409_CONFLICT,
            )

        # Per-user limit: max 2 concurrent
        active_count = SparkDeployment.objects.filter(
            user=request.user,
            status__in=['pending', 'deploying'],
        ).count()
        if active_count >= 2:
            return Response(
                {"error": "Too many concurrent deployments (max 2)"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Resolve auth context
        from authentication.jwt_utils import JWTManager

        auth_token = JWTManager.create_access_token(request.user)
        orchestrator_url = "http://orchestrator:8003"
        chat_id = str(spark.chat_id) if spark.chat_id else str(spark.id)[:8]
        conversation_id = (
            str(spark.chat.conversation_id) if spark.chat else str(spark.id)
        )

        # Create deployment record
        deployment = SparkDeployment.objects.create(
            spark=spark, user=request.user
        )

        # Run in background thread
        user_id = str(request.user.id)
        deployment_id = str(deployment.id)

        def _run():
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                from llm.ignite_service import deploy_spark_to_vercel

                loop.run_until_complete(
                    deploy_spark_to_vercel(
                        spark_id=str(spark.id),
                        user_id=user_id,
                        auth_token=auth_token,
                        orchestrator_url=orchestrator_url,
                        chat_id=chat_id,
                        conversation_id=conversation_id,
                        deployment_id=deployment_id,
                    )
                )
            except Exception:
                logger.exception("Deploy background thread failed")
                SparkDeployment.objects.filter(id=deployment.id).exclude(
                    status__in=['deployed', 'failed']
                ).update(
                    status='failed',
                    error_message='Deployment thread crashed unexpectedly',
                )
            finally:
                loop.close()

        threading.Thread(target=_run, daemon=True).start()

        return Response(
            SparkDeploymentSerializer(deployment).data,
            status=status.HTTP_202_ACCEPTED,
        )


class AppViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for App management.

    list: List apps (latest version per spark) for the authenticated user.
    retrieve: Get a single app with full details.
    start_preview: Start the dev server for an app.
    stop_preview: Stop the dev server for an app.
    preview_status: Check if the dev server is running.
    versions: List all versions of an app's spark.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = SparkPagination

    def get_queryset(self):
        from django.db.models import OuterRef, Subquery

        base_qs = App.objects.filter(user=self.request.user).select_related('spark', 'chat')

        if self.action == 'list':
            latest_version_subquery = App.objects.filter(
                spark=OuterRef('spark'),
                user=self.request.user,
            ).order_by('-version').values('id')[:1]
            base_qs = base_qs.filter(id__in=Subquery(latest_version_subquery))

            chat_id = self.request.query_params.get('chat_id')
            if chat_id:
                base_qs = base_qs.filter(chat_id=chat_id)

        return base_qs

    def get_serializer_class(self):
        if self.action == 'list':
            return AppListSerializer
        return AppSerializer

    @action(detail=True, methods=['post'])
    def start_preview(self, request, pk=None):
        """Start the dev server for this app."""
        app = self.get_object()

        from authentication.jwt_utils import JWTManager
        auth_token = JWTManager.create_access_token(request.user)

        chat_id = str(app.chat_id) if app.chat_id else str(app.id)[:8]
        conversation_id = (
            str(app.chat.conversation_id)
            if app.chat and app.chat.conversation
            else str(app.id)
        )

        # Step 1: Ensure workspace exists — restore files from persistent storage
        # The sandbox tmpfs wipes /workspace on container recycle, so we must
        # restore before starting the process.
        auth_headers = {"Authorization": f"Bearer {auth_token}"}
        try:
            restore_resp = httpx.post(
                "http://orchestrator:8003/workspace/restore",
                json={
                    "user_id": str(request.user.id),
                    "chat_id": chat_id,
                    "force": False,
                },
                headers=auth_headers,
                timeout=30.0,
            )
            if restore_resp.status_code == 200:
                restore_data = restore_resp.json()
                logger.info(
                    f"[start_preview] Workspace restore: "
                    f"success={restore_data.get('success')}, "
                    f"files_synced={restore_data.get('files_synced', 0)}, "
                    f"was_restored={restore_data.get('was_restored')}"
                )
                if not restore_data.get("success"):
                    return Response(
                        {'error': 'Failed to restore workspace files. The project may need to be re-ignited.'},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
            else:
                logger.warning(f"[start_preview] Workspace restore HTTP {restore_resp.status_code}")
        except httpx.RequestError as e:
            logger.warning(f"[start_preview] Workspace restore failed: {e}")

        # Step 1.5: Install dependencies if node_modules is missing
        try:
            install_resp = httpx.post(
                "http://orchestrator:8003/fs/bash",
                json={
                    "user_id": str(request.user.id),
                    "conversation_id": conversation_id,
                    "chat_id": chat_id,
                    "command": f"cd /workspace/chat-{chat_id}/{app.project_path} && {{ [ -d node_modules ] && echo 'node_modules exists, skipping install' || npm install; }}",
                    "timeout": 90,
                    "sync_mode": True,
                },
                headers=auth_headers,
                timeout=95.0,
            )
            if install_resp.status_code == 200:
                install_data = install_resp.json()
                exit_code = install_data.get('exit_code', -1)
                logger.info(
                    f"[start_preview] npm install: exit_code={exit_code}, "
                    f"time={install_data.get('execution_time', 0):.1f}s"
                )
                if exit_code != 0:
                    return Response(
                        {'error': 'Dependency installation failed. The project may need to be re-ignited.'},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )
            else:
                logger.warning(f"[start_preview] npm install HTTP {install_resp.status_code}")
                return Response(
                    {'error': 'Failed to install dependencies. Try again or re-ignite the project.'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
        except httpx.TimeoutException:
            return Response(
                {'error': 'Dependency installation timed out (90s). Try again — cached packages may make it faster.'},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except httpx.RequestError as e:
            logger.warning(f"[start_preview] npm install failed: {e}")
            return Response(
                {'error': f'Failed to reach orchestrator for npm install: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Step 2: Start the dev server
        command = f"npm run dev --prefix {app.project_path}"
        port = 3000

        try:
            response = httpx.post(
                "http://orchestrator:8003/processes/start",
                json={
                    "user_id": str(request.user.id),
                    "conversation_id": conversation_id,
                    "chat_id": chat_id,
                    "command": command,
                    "port": port,
                    "sync_mode": True,
                },
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=15.0,
            )
        except httpx.RequestError as e:
            return Response(
                {'error': f'Failed to reach orchestrator: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != 200:
            try:
                detail = response.json().get("detail", f"Orchestrator error: HTTP {response.status_code}")
            except Exception:
                detail = f"Orchestrator error: HTTP {response.status_code}"
            if not isinstance(detail, str):
                detail = str(detail)
            return Response({'error': detail}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(response.json())

    @action(detail=True, methods=['post'])
    def stop_preview(self, request, pk=None):
        """Stop the dev server. Looks up the running port server-side."""
        app = self.get_object()

        from authentication.jwt_utils import JWTManager
        auth_token = JWTManager.create_access_token(request.user)

        chat_id = str(app.chat_id) if app.chat_id else str(app.id)[:8]
        conversation_id = (
            str(app.chat.conversation_id)
            if app.chat and app.chat.conversation
            else str(app.id)
        )

        # Optional port hint from frontend
        port = request.data.get('port')
        if not port:
            try:
                list_resp = httpx.get(
                    f"http://orchestrator:8003/processes/{request.user.id}",
                    params={"chat_id": chat_id},
                    headers={"Authorization": f"Bearer {auth_token}"},
                    timeout=5.0,
                )
                if list_resp.status_code == 200:
                    processes = list_resp.json()
                    match = next(
                        (p for p in processes if app.project_path in p.get('command', '')),
                        None,
                    )
                    if match:
                        port = match['port']
                    else:
                        logger.warning(
                            f"[stop_preview] No process matched project_path={app.project_path} "
                            f"in {len(processes)} processes for user {request.user.id}"
                        )
            except Exception as e:
                logger.debug(f"[stop_preview] Failed to list processes: {e}")

        if not port:
            return Response(
                {'error': 'No running preview found for this app'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            response = httpx.post(
                "http://orchestrator:8003/processes/stop-by-port",
                json={
                    "user_id": str(request.user.id),
                    "conversation_id": conversation_id,
                    "port": port,
                },
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=10.0,
            )
        except httpx.RequestError as e:
            return Response(
                {'error': f'Failed to reach orchestrator: {e}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if response.status_code != 200:
            try:
                detail = response.json().get("detail", f"HTTP {response.status_code}")
            except Exception:
                detail = f"HTTP {response.status_code}"
            if not isinstance(detail, str):
                detail = str(detail)
            return Response({'error': detail}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({'success': True, 'port': port})

    @action(detail=True, methods=['get'])
    def preview_status(self, request, pk=None):
        """Check if the dev server is running for this app."""
        app = self.get_object()

        from authentication.jwt_utils import JWTManager
        auth_token = JWTManager.create_access_token(request.user)

        chat_id = str(app.chat_id) if app.chat_id else str(app.id)[:8]

        try:
            list_resp = httpx.get(
                f"http://orchestrator:8003/processes/{request.user.id}",
                params={"chat_id": chat_id},
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=5.0,
            )
            if list_resp.status_code == 200:
                processes = list_resp.json()
                match = next(
                    (p for p in processes if app.project_path in p.get('command', '')),
                    None,
                )
                if match:
                    return Response({'running': True, 'port': match['port']})
        except Exception as e:
            logger.debug(f"[preview_status] Failed to check processes: {e}")

        return Response({'running': False, 'port': None})

    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """List all versions of this app's spark."""
        app = self.get_object()
        all_versions = App.objects.filter(
            spark=app.spark,
            user=request.user,
        ).order_by('-version')
        serializer = AppListSerializer(all_versions, many=True)
        return Response(serializer.data)
