"""
Workspace persistence models.

These models store user workspace files to PostgreSQL (small files inline)
and Cloudflare R2 (large files), enabling quick sandbox destruction while
persisting user data across sessions.
"""
import uuid
from django.db import models
from django.conf import settings


class Workspace(models.Model):
    """
    Represents a user's workspace for a specific chat.
    One workspace per user per chat. Each chat within a conversation
    has its own isolated workspace files (sandbox dir: workspace/chat-<chat_id>/).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspaces'
    )
    chat = models.ForeignKey(
        'conversations.Chat',
        on_delete=models.CASCADE,
        related_name='workspaces'
    )
    name = models.CharField(max_length=255, blank=True)

    # Stats
    total_size_bytes = models.BigIntegerField(default=0)
    file_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'chat')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['last_accessed_at']),
        ]
        ordering = ['-last_accessed_at']

    def __str__(self):
        return f"Workspace {self.id} (user={self.user_id}, chat={self.chat_id})"

    def update_stats(self):
        """Update workspace stats from files."""
        from django.db.models import Sum, Count
        stats = self.files.aggregate(
            total_size=Sum('size_bytes'),
            count=Count('id')
        )
        self.total_size_bytes = stats['total_size'] or 0
        self.file_count = stats['count'] or 0
        self.save(update_fields=['total_size_bytes', 'file_count', 'updated_at'])


class WorkspaceFile(models.Model):
    """
    Represents a file in a workspace.
    Small files (<256KB) store content inline, larger files reference R2.
    """
    STORAGE_INLINE = 'inline'
    STORAGE_R2 = 'r2'
    STORAGE_CHOICES = [
        (STORAGE_INLINE, 'Inline (PostgreSQL)'),
        (STORAGE_R2, 'R2 (Cloudflare)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='files'
    )

    # File info
    path = models.CharField(max_length=1024)  # relative: "src/main.py"
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127, blank=True, null=True)
    size_bytes = models.BigIntegerField()

    # Storage strategy
    storage_type = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default=STORAGE_INLINE
    )

    # Inline storage (small files)
    content = models.BinaryField(blank=True, null=True)

    # R2 storage (large files)
    r2_bucket = models.CharField(max_length=63, blank=True, null=True)
    r2_key = models.CharField(max_length=1024, blank=True, null=True)

    # Integrity
    sha256_hash = models.CharField(max_length=64, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('workspace', 'path')
        indexes = [
            models.Index(fields=['workspace']),
            models.Index(fields=['sha256_hash']),
        ]
        ordering = ['path']

    def __str__(self):
        storage = "inline" if self.storage_type == self.STORAGE_INLINE else "R2"
        return f"{self.path} ({self.size_bytes} bytes, {storage})"


class SyncState(models.Model):
    """Tracks sync state for a workspace."""
    STATUS_IDLE = 'idle'
    STATUS_SYNCING = 'syncing'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_IDLE, 'Idle'),
        (STATUS_SYNCING, 'Syncing'),
        (STATUS_ERROR, 'Error'),
    ]

    DIRECTION_SAVE = 'save'
    DIRECTION_RESTORE = 'restore'
    DIRECTION_CHOICES = [
        (DIRECTION_SAVE, 'Save'),
        (DIRECTION_RESTORE, 'Restore'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.OneToOneField(
        Workspace,
        on_delete=models.CASCADE,
        related_name='sync_state'
    )

    # Sync info
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IDLE
    )
    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        blank=True,
        null=True
    )

    # Progress
    files_total = models.IntegerField(default=0)
    files_synced = models.IntegerField(default=0)
    bytes_total = models.BigIntegerField(default=0)
    bytes_synced = models.BigIntegerField(default=0)

    # Timestamps
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Sync State'
        verbose_name_plural = 'Sync States'

    def __str__(self):
        return f"SyncState for {self.workspace_id}: {self.status}"

    @property
    def progress_percent(self) -> int:
        """Get sync progress as percentage."""
        if self.files_total == 0:
            return 0
        return int((self.files_synced / self.files_total) * 100)


class Asset(models.Model):
    """
    Media assets attached to chats (images, videos, thumbnails).

    These are NOT IDE workspace files - they're chat attachments like:
    - User-uploaded images/videos in chat messages
    - AI-generated images
    - Thumbnails and previews

    R2 path structure: {user_id}/chats/{chat_id}/assets/{asset_id}
    """

    # Asset types
    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_AUDIO = 'audio'
    TYPE_THUMBNAIL = 'thumbnail'
    TYPE_GENERATED = 'generated'  # AI-generated content
    TYPE_DOCUMENT = 'document'  # Documents (PDF, text, code, etc.)
    TYPE_CHOICES = [
        (TYPE_IMAGE, 'Image'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_AUDIO, 'Audio'),
        (TYPE_THUMBNAIL, 'Thumbnail'),
        (TYPE_GENERATED, 'AI Generated'),
        (TYPE_DOCUMENT, 'Document'),
    ]

    # Storage types (same as WorkspaceFile)
    STORAGE_INLINE = 'inline'
    STORAGE_R2 = 'r2'
    STORAGE_CHOICES = [
        (STORAGE_INLINE, 'Inline (PostgreSQL)'),
        (STORAGE_R2, 'R2 (Cloudflare)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Owner and context
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assets'
    )
    chat = models.ForeignKey(
        'conversations.Chat',
        on_delete=models.CASCADE,
        related_name='assets'
    )
    message = models.ForeignKey(
        'conversations.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assets',
        help_text="Optional: specific message this asset is attached to"
    )

    # Asset info
    asset_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_IMAGE
    )
    filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=127)
    size_bytes = models.BigIntegerField()

    # Storage strategy
    storage_type = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default=STORAGE_R2  # Assets typically go to R2 (images are large)
    )

    # Inline storage (small assets like tiny thumbnails)
    content = models.BinaryField(blank=True, null=True)

    # R2 storage
    r2_bucket = models.CharField(max_length=63, blank=True, null=True)
    r2_key = models.CharField(
        max_length=1024,
        blank=True,
        null=True,
        help_text="R2 key: {user_id}/chats/{chat_id}/assets/{asset_id}"
    )

    # Media metadata
    width = models.IntegerField(null=True, blank=True, help_text="Image/video width in pixels")
    height = models.IntegerField(null=True, blank=True, help_text="Image/video height in pixels")
    duration_seconds = models.FloatField(null=True, blank=True, help_text="Video/audio duration")

    # Thumbnail reference (for videos/large images)
    thumbnail = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_assets',
        help_text="Thumbnail asset for this video/image"
    )

    # Integrity
    sha256_hash = models.CharField(max_length=64, db_index=True)

    # Generation metadata (for AI-generated assets)
    generation_prompt = models.TextField(
        blank=True,
        null=True,
        help_text="Prompt used to generate this asset (if AI-generated)"
    )
    generation_model = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Model used to generate this asset (e.g., 'dall-e-3')"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'chat']),
            models.Index(fields=['chat', 'message']),
            models.Index(fields=['asset_type']),
            models.Index(fields=['sha256_hash']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.asset_type}: {self.filename} ({self.size_bytes} bytes)"

    @property
    def is_image(self) -> bool:
        return self.asset_type in (self.TYPE_IMAGE, self.TYPE_GENERATED)

    @property
    def is_video(self) -> bool:
        return self.asset_type == self.TYPE_VIDEO

    @property
    def has_thumbnail(self) -> bool:
        return self.thumbnail is not None


class AssetShareLink(models.Model):
    """
    Public share links for assets (images, videos).

    Enables users to share AI-generated content via unique URLs.
    Supports expiration, view tracking, and revocation.

    Industry-standard pattern used by ChatGPT, Runway, Midjourney.
    """
    import secrets

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    # Core relationships
    asset = models.ForeignKey(
        'Asset',
        on_delete=models.CASCADE,
        related_name='share_links',
        help_text="The asset being shared"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='asset_share_links',
        help_text="User who created the share link"
    )

    # Share token (cryptographically secure)
    token = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="URL-safe token for public access"
    )

    # Lifecycle management
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether the link is active (soft delete)"
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional expiration timestamp"
    )

    # Analytics
    view_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this link has been accessed"
    )
    last_viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time someone viewed this shared asset"
    )

    # Optional title override (for social sharing)
    custom_title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Custom title for social media previews"
    )

    # Watermark settings (captured at share creation)
    WATERMARK_POSITIONS = [
        ('bottom-right', 'Bottom Right'),
        ('bottom-left', 'Bottom Left'),
        ('top-right', 'Top Right'),
        ('top-left', 'Top Left'),
    ]
    watermark_enabled = models.BooleanField(
        default=True,
        help_text="Whether to apply watermark to shared images"
    )
    watermark_position = models.CharField(
        max_length=20,
        choices=WATERMARK_POSITIONS,
        default='bottom-right',
        help_text="Position of watermark on image"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['asset', 'is_active']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Share({self.token[:8]}...) for {self.asset_id}"

    @property
    def is_expired(self) -> bool:
        """Check if the link has expired."""
        from django.utils import timezone
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if the link is active and not expired."""
        return self.is_active and not self.is_expired

    def increment_view_count(self):
        """Atomically increment the view count."""
        from django.db.models import F
        from django.utils import timezone
        AssetShareLink.objects.filter(pk=self.pk).update(
            view_count=F('view_count') + 1,
            last_viewed_at=timezone.now()
        )

    @classmethod
    def generate_token(cls) -> str:
        """Generate a cryptographically secure URL-safe token."""
        import secrets
        return secrets.token_urlsafe(32)  # 43 characters


class FileVersionContent(models.Model):
    """
    Deduplicated content storage for file versions.

    Multiple FileVersions can reference the same content via sha256_hash,
    enabling efficient storage when files haven't changed or are duplicated.

    Uses same tiered storage pattern as WorkspaceFile:
    - Small content (<256KB): stored inline in PostgreSQL
    - Large content (>=256KB): stored in Cloudflare R2
    """
    sha256_hash = models.CharField(max_length=64, primary_key=True)

    # Tiered storage (reuse existing pattern)
    STORAGE_INLINE = 'inline'
    STORAGE_R2 = 'r2'
    STORAGE_CHOICES = [
        (STORAGE_INLINE, 'Inline (PostgreSQL)'),
        (STORAGE_R2, 'R2 (Cloudflare)'),
    ]
    storage_type = models.CharField(
        max_length=10,
        choices=STORAGE_CHOICES,
        default=STORAGE_INLINE
    )
    content = models.BinaryField(blank=True, null=True)  # For inline storage
    r2_key = models.CharField(max_length=1024, blank=True)  # For R2 storage

    # Metadata
    size_bytes = models.BigIntegerField()
    reference_count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'workspaces_file_version_content'
        verbose_name = 'File Version Content'
        verbose_name_plural = 'File Version Contents'

    def __str__(self):
        return f"{self.sha256_hash[:12]}... ({self.size_bytes} bytes, {self.storage_type})"


class FileVersion(models.Model):
    """
    Immutable snapshot of a file at a point in time.

    Every modification to a workspace file creates a new version, enabling:
    - Full file history per file
    - Diff viewing between any two versions
    - Tracking who/what modified files (user, file tools, coding agent)
    - Workspace-wide timeline of changes

    Content is stored via FileVersionContent for deduplication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='file_versions'
    )
    path = models.CharField(max_length=1024, db_index=True)
    version_number = models.PositiveIntegerField()

    # What caused this version
    class SourceType(models.TextChoices):
        USER_EDIT = 'user_edit', 'User Edit'
        FILE_TOOL = 'file_tool', 'File Tool'
        CODING_AGENT = 'coding_agent', 'Coding Agent'
        UPLOAD = 'upload', 'Upload'
        RESTORE = 'restore', 'Restore'
        INITIAL = 'initial', 'Initial'

    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_message = models.ForeignKey(
        'conversations.Message',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='file_versions'
    )
    source_job_id = models.CharField(max_length=50, blank=True)
    source_tool_name = models.CharField(max_length=50, blank=True)

    # Reference to deduplicated content
    content_ref = models.ForeignKey(
        FileVersionContent,
        on_delete=models.PROTECT,
        to_field='sha256_hash',
        db_column='sha256_hash',
        related_name='versions'
    )

    # Denormalized for quick access (avoid joins)
    size_bytes = models.BigIntegerField()
    is_deleted = models.BooleanField(default=False)
    is_binary = models.BooleanField(default=False)
    mime_type = models.CharField(max_length=127, blank=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='file_versions_created'
    )

    class Meta:
        db_table = 'workspaces_file_version'
        unique_together = ['workspace', 'path', 'version_number']
        ordering = ['path', '-version_number']
        indexes = [
            models.Index(fields=['workspace', 'path', 'created_at']),
            models.Index(fields=['workspace', 'created_at']),
            models.Index(fields=['source_type']),
            models.Index(fields=['source_message']),
        ]

    def __str__(self):
        return f"{self.path} v{self.version_number} ({self.source_type})"

    @classmethod
    def get_next_version_number(cls, workspace, path: str) -> int:
        """Get the next version number for a file in a workspace."""
        last = cls.objects.filter(
            workspace=workspace,
            path=path
        ).order_by('-version_number').first()
        return (last.version_number + 1) if last else 1

    @property
    def sha256_hash(self) -> str:
        """Convenience accessor for content hash."""
        return self.content_ref_id
