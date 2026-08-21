from django.contrib import admin
from .models import SupportRequest
from . import notifications as support_notifications


class ReplyForm(admin.ModelAdmin):
    """
    Admin for SupportRequest. Saving with a non-empty reply_body fires
    send_support_reply_email and updates status to in_progress.
    """
    list_display = ("subject", "email", "status", "assigned_to", "created_at")
    list_filter = ("status", "assigned_to")
    search_fields = ("email", "subject", "message")
    readonly_fields = ("id", "user", "email", "subject", "message", "context", "created_at")
    raw_id_fields = ("assigned_to",)

    fieldsets = (
        ("Request", {
            "fields": ("id", "user", "email", "subject", "message", "context", "created_at"),
        }),
        ("Management", {
            "fields": ("status", "assigned_to"),
        }),
        ("Reply", {
            "fields": ("reply_body",),
            "description": "Compose a reply. Saving sends an email to the user.",
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        from django import forms
        form.base_fields["reply_body"] = forms.CharField(
            widget=forms.Textarea(attrs={"rows": 6}),
            required=False,
            label="Reply body (HTML allowed)",
        )
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        reply_body = form.cleaned_data.get("reply_body", "").strip()
        if reply_body:
            try:
                support_notifications.send_support_reply_email(obj, reply_body)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Failed to send reply email for support request %s", obj.id
                )


admin.site.register(SupportRequest, ReplyForm)
