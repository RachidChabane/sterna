# Container Architecture - User-based Isolation

## Overview

The sandbox container system has been refactored to use **one container per user** instead of one container per chat. This dramatically reduces resource usage while maintaining isolation between chats.

## Architecture Changes

### Before (Per-Chat Containers)
```
User A:
  - Container: sandbox-exec-userA-chat1  (/workspace/)
  - Container: sandbox-exec-userA-chat2  (/workspace/)
  - Container: sandbox-exec-userA-chat3  (/workspace/)

User B:
  - Container: sandbox-exec-userB-chat1  (/workspace/)
  - Container: sandbox-exec-userB-chat2  (/workspace/)
```

**Problems:**
- Too many containers (one per chat)
- High resource overhead
- Slow container startup for each new chat

### After (Per-User Containers with Chat Folders)
```
User A:
  - Container: sandbox-exec-userA
    - /workspace/chat-chat1/
    - /workspace/chat-chat2/
    - /workspace/chat-chat3/

User B:
  - Container: sandbox-exec-userB
    - /workspace/chat-chat1/
    - /workspace/chat-chat2/
```

**Benefits:**
- One container per user (much fewer containers)
- Instant access to existing container
- Isolation maintained via chat folders
- Same ephemeral behavior (container destroyed after inactivity)

## Implementation Details

### Container Lifecycle

1. **Container Creation**
   - Created on first file operation for a user
   - Container ID: `sandbox-exec-{user_id}`
   - Workspace size increased to 2GB (holds multiple chat folders)

2. **Chat Isolation**
   - Each chat gets its own folder: `/workspace/chat-{chat_id}/`
   - Chat folder created automatically on first access
   - All file operations scoped to chat folder

3. **Container Destruction**
   - Same inactivity timeout (1 hour by default)
   - Container destroyed when no activity from ANY chat
   - All chat folders destroyed with container (ephemeral)

### File Path Translation

The backend automatically translates frontend paths to chat-scoped paths:

```python
Frontend path:  /workspace/myfile.py
Backend path:   /workspace/chat-{chat_id}/myfile.py

Frontend path:  /workspace/src/app.py
Backend path:   /workspace/chat-{chat_id}/src/app.py
```

This translation is **completely transparent** to the frontend.

### Key Functions

#### `_generate_sandbox_id(user_id, conversation_id, chat_id, sync_mode)`
```python
# Returns: sandbox-exec-{user_id}
# One container per user
```

#### `_get_chat_workspace_path(chat_id, conversation_id)`
```python
# Returns: /workspace/chat-{chat_id}
# Chat-specific folder within container
```

#### All file operations (list_files, read_file, write_file, etc.)
- Automatically translate paths to chat folders
- Ensure chat folder exists before operations
- Return paths in frontend format (/workspace/...)

## Resource Savings

### Example with 100 Users

**Before:**
- Average: 5 chats per user
- Total containers: 500 containers
- Memory: ~256GB (500 × 512MB)

**After:**
- Total containers: 100 containers (one per user)
- Memory: ~51.2GB (100 × 512MB)
- **Savings: 80% fewer containers, 80% less memory**

## Frontend Compatibility

**No frontend changes required!** The refactoring is backend-only:

- Frontend continues to use `/workspace/` paths
- Backend translates to chat folders transparently
- All existing API calls work unchanged
- chat_id is already passed in all requests

## File Operations

All file operations are chat-scoped:

1. **list_files(/workspace)** → Lists `/workspace/chat-{chat_id}/`
2. **read_file(/workspace/app.py)** → Reads `/workspace/chat-{chat_id}/app.py`
3. **write_file(/workspace/app.py)** → Writes `/workspace/chat-{chat_id}/app.py`
4. **delete_file(/workspace/app.py)** → Deletes `/workspace/chat-{chat_id}/app.py`
5. **rename_file(old, new)** → Renames within `/workspace/chat-{chat_id}/`
6. **create_directory(/workspace/src)** → Creates `/workspace/chat-{chat_id}/src/`
7. **get_file_metadata(/workspace/app.py)** → Gets metadata for `/workspace/chat-{chat_id}/app.py`

## Metadata Storage

Model metadata (tracking which AI model created/modified files) is now stored separately but isolated per chat:

**Old location:** `/metadata/{path}/{filename}.meta.json` (shared across all chats)
**New location:** `/workspace/metadata-{chat_id}/{path}/{filename}.meta.json` (isolated per chat)

Structure example:
```
/workspace/
├── chat-abc123/                    # Chat files
│   └── app.py
└── metadata-abc123/                # Chat metadata (separate folder)
    └── app.py.meta.json
```

Benefits:
- **Chat isolation:** Each chat has its own metadata folder, no cross-contamination
- **Automatic cleanup:** Metadata is destroyed with the container (ephemeral)
- **Workspace integration:** Metadata lives in the same tmpfs as files
- **Separate from files:** Metadata not mixed with chat files in IDE

## Code Execution

Code execution is also chat-scoped:

```python
# Frontend sends code to execute
execute_code(code="print('hello')", language="python", chat_id="abc123")

# Backend runs in chat workspace
workdir = /workspace/chat-abc123/
```

This ensures:
- Code can access files in its chat folder
- Code cannot access files from other chats
- Isolation is maintained

## Security

- **Isolation maintained:** Each chat has its own folder
- **No cross-chat access:** File operations are scoped
- **Same security model:** gVisor runtime, resource limits, etc.
- **Ephemeral:** Containers destroyed after inactivity

## Migration Notes

### Existing Containers

Existing per-chat containers will be automatically cleaned up:
- `_cleanup_orphaned_containers()` removes old containers on startup
- Old container naming pattern no longer created

### Existing Data

**Important:** All data in containers is ephemeral (tmpfs).
- No migration needed - data is temporary anyway
- Users will see empty workspaces on first access

## Configuration

### Environment Variables

- `INACTIVITY_TIMEOUT`: Container timeout (default: 3600s / 1 hour)
- `CLEANUP_INTERVAL`: Cleanup check interval (default: 60s)

### Resource Limits (per container)

- **Memory:** 512MB
- **CPU:** 1 core
- **PIDs:** 100
- **Workspace:** 2GB tmpfs (increased from 500MB)

## Monitoring

### Container Metrics

```bash
# List active containers
docker ps --filter "name=sandbox-exec-"

# View logs for a user's container
docker logs sandbox-exec-{user_id}

# Check resource usage
docker stats sandbox-exec-{user_id}
```

### Chat Folders

```bash
# List chat folders in a container
docker exec sandbox-exec-{user_id} ls -la /workspace/

# Check chat folder size
docker exec sandbox-exec-{user_id} du -sh /workspace/chat-*
```

## Troubleshooting

### Container not found
- Container may have been destroyed due to inactivity
- Will be recreated automatically on next file operation

### Files disappeared
- Container was destroyed (ephemeral)
- This is expected behavior after inactivity timeout

### Permission errors
- Check container logs: `docker logs sandbox-exec-{user_id}`
- Verify chat_id is being passed correctly

## Future Enhancements

### Potential Improvements

1. **Persistent storage:** Optional volume mounts for chat folders
2. **Resource quotas:** Per-chat folder size limits
3. **Shared folders:** Allow file sharing between chats (opt-in)
4. **Snapshot/restore:** Save/restore chat workspace state

### Performance Optimizations

1. **Lazy folder creation:** Only create chat folders when files are written
2. **Folder cleanup:** Remove empty chat folders to save space
3. **Compression:** Compress inactive chat folders

## Related Files

- `sandbox/orchestrator/sandbox_executor.py` - Main implementation
- `api/sandbox_views.py` - API proxy (unchanged)
- `frontend/src/api/fs.ts` - Frontend API client (unchanged)
- `frontend/src/components/sandbox/FullIDE.tsx` - IDE component (unchanged)
