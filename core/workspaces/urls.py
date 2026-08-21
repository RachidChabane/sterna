"""URL configuration for workspaces API."""
from django.urls import path

from .api import views
from .api import version_views

app_name = 'workspaces'

urlpatterns = [
    # Workspace sync endpoints (called by orchestrator)
    path('save/', views.save_workspace, name='save'),
    path('restore/<str:user_id>/<str:chat_id>/', views.restore_workspace, name='restore'),
    path('info/<str:user_id>/<str:chat_id>/', views.workspace_info, name='info'),
    path('delete/<str:user_id>/<str:chat_id>/', views.delete_workspace, name='delete'),
    path('list/<str:user_id>/', views.list_user_workspaces, name='list'),

    # Health check endpoint
    path('storage/health/', views.storage_health, name='storage-health'),

    # File versioning endpoints
    path('<str:chat_id>/files/history/', version_views.file_history, name='file-history'),
    path('<str:chat_id>/timeline/', version_views.workspace_timeline, name='workspace-timeline'),
    path('versions/<str:version_id>/content/', version_views.version_content, name='version-content'),
    path('versions/compare/', version_views.compare_versions, name='compare-versions'),
    path('messages/<str:message_id>/file-changes/', version_views.message_file_changes, name='message-file-changes'),
    path('jobs/<str:job_id>/file-changes/', version_views.job_file_changes, name='job-file-changes'),

    # Version creation endpoints (called by orchestrator)
    path('versions/create/', version_views.create_version, name='version-create'),
    path('versions/create-batch/', version_views.create_versions_batch, name='versions-create-batch'),

    # Asset endpoints (for chat attachments)
    path('assets/upload/', views.upload_asset, name='asset-upload'),
    path('assets/user/images/', views.list_user_generated_images, name='user-generated-images'),
    path('assets/user/videos/', views.list_user_generated_videos, name='user-generated-videos'),
    path('assets/<str:asset_id>/', views.get_asset, name='asset-get'),
    path('assets/<str:asset_id>/download/', views.download_asset, name='asset-download'),
    path('assets/<str:asset_id>/presigned-url/', views.get_asset_presigned_url, name='asset-presigned-url'),
    path('assets/<str:asset_id>/delete/', views.delete_asset, name='asset-delete'),
    path('assets/chat/<str:chat_id>/', views.list_chat_assets, name='assets-by-chat'),
    path('assets/message/<str:message_id>/', views.list_message_assets, name='assets-by-message'),

    # Share link management endpoints (authenticated)
    path('assets/<str:asset_id>/share/', views.create_share_link, name='asset-share-create'),
    path('assets/<str:asset_id>/shares/', views.get_asset_share_links, name='asset-share-list'),
    path('assets/share/<str:token>/revoke/', views.revoke_share_link, name='asset-share-revoke'),
    path('assets/shares/', views.list_share_links, name='user-share-links'),
]
