from django.contrib import admin
from .models import Workspace, WorkspaceFile, SyncState


class WorkspaceFileInline(admin.TabularInline):
    model = WorkspaceFile
    extra = 0
    readonly_fields = ('id', 'sha256_hash', 'created_at', 'updated_at')
    fields = ('path', 'filename', 'size_bytes', 'storage_type', 'sha256_hash', 'updated_at')


class SyncStateInline(admin.StackedInline):
    model = SyncState
    extra = 0
    readonly_fields = ('id', 'started_at', 'completed_at')


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'chat', 'file_count', 'total_size_display', 'last_accessed_at')
    list_filter = ('created_at', 'last_accessed_at')
    search_fields = ('id', 'user__email', 'chat__id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_accessed_at')
    inlines = [SyncStateInline, WorkspaceFileInline]

    @admin.display(description='Total Size')
    def total_size_display(self, obj):
        """Display total size in human-readable format."""
        size = obj.total_size_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@admin.register(WorkspaceFile)
class WorkspaceFileAdmin(admin.ModelAdmin):
    list_display = ('path', 'workspace', 'size_display', 'storage_type', 'updated_at')
    list_filter = ('storage_type', 'created_at')
    search_fields = ('path', 'filename', 'workspace__id')
    readonly_fields = ('id', 'sha256_hash', 'created_at', 'updated_at')

    @admin.display(description='Size')
    def size_display(self, obj):
        """Display size in human-readable format."""
        size = obj.size_bytes
        for unit in ['B', 'KB', 'MB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


@admin.register(SyncState)
class SyncStateAdmin(admin.ModelAdmin):
    list_display = ('workspace', 'status', 'direction', 'progress_percent', 'started_at', 'completed_at')
    list_filter = ('status', 'direction')
    readonly_fields = ('id', 'started_at', 'completed_at')
