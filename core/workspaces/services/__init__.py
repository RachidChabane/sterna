# Lazy imports to avoid dependency issues
# sync_service requires aiofiles which may not be installed in all environments

from .workspace_storage import WorkspaceStorageService, get_storage_service
from .asset_storage import AssetStorageService, get_asset_storage_service
from .file_version_service import FileVersionService, get_file_version_service

__all__ = [
    'WorkspaceStorageService',
    'get_storage_service',
    'AssetStorageService',
    'get_asset_storage_service',
    'FileVersionService',
    'get_file_version_service',
]

# Lazy import for WorkspaceSyncService (has async dependencies)
def __getattr__(name):
    if name == 'WorkspaceSyncService':
        from .sync_service import WorkspaceSyncService
        return WorkspaceSyncService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
