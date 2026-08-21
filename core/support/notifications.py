import logging
import os
import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SUPPORT_SLACK_WEBHOOK = os.environ.get("SUPPORT_SLACK_WEBHOOK_URL", "")


def send_support_request_received_email(instance):
    """Send auto-ack to the user who submitted the request."""
    context = {
        "email": instance.email,
        "subject": instance.subject,
        "message": instance.message,
    }
    text_body = render_to_string("email/support_request_received.txt", context)
    html_body = render_to_string("email/support_request_received.html", context)

    msg = EmailMultiAlternatives(
        subject="We received your support request",
        body=text_body,
        from_email=settings.SUPPORT_EMAIL,
        to=[instance.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


def send_support_reply_email(instance, reply_body: str):
    """Send admin-composed reply to the user."""
    context = {
        "email": instance.email,
        "subject": instance.subject,
        "reply_body": reply_body,
    }
    text_body = render_to_string("email/support_reply.txt", context)
    html_body = render_to_string("email/support_reply.html", context)

    msg = EmailMultiAlternatives(
        subject=f"Re: {instance.subject}",
        body=text_body,
        from_email=settings.SUPPORT_EMAIL,
        to=[instance.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)


def post_to_slack(instance):
    """Post new support request to the support Slack webhook."""
    if not SUPPORT_SLACK_WEBHOOK:
        logger.debug("SUPPORT_SLACK_WEBHOOK_URL not configured — skipping Slack post")
        return

    plan = instance.context.get("plan", "unknown")
    route = instance.context.get("route", "unknown")
    browser = instance.context.get("browser", "unknown")

    payload = {
        "text": (
            f":sos: *New support request*\n"
            f"*From:* {instance.email} (plan: {plan})\n"
            f"*Subject:* {instance.subject}\n"
            f"*Route:* {route} | *Browser:* {browser}\n"
            f"*Message:*\n```{instance.message[:500]}```"
        )
    }
    resp = requests.post(SUPPORT_SLACK_WEBHOOK, json=payload, timeout=5)
    resp.raise_for_status()
