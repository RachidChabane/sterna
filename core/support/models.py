import uuid
from django.db import models
from django.conf import settings


class SupportRequest(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_requests",
    )
    # Required for anon submissions; pre-filled from user.email for auth users
    email = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    # Captures route, browser, user-agent, plan from frontend
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="new", db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_requests",
        limit_choices_to={"is_staff": True},
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Support Request"
        verbose_name_plural = "Support Requests"

    def __str__(self):
        return f"[{self.status}] {self.subject} — {self.email}"
