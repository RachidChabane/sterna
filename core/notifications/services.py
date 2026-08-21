import logging
from types import SimpleNamespace
from typing import Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.translation import override

logger = logging.getLogger(__name__)


def _build_context(user, **extra) -> dict:
    return {
        "user": user,
        "brand_name": settings.BRAND_NAME,
        "support_email": settings.SUPPORT_EMAIL,
        **extra,
    }


def _send(
    *,
    template_base: str,
    context: dict,
    to_email: str,
    subject: str,
    language: str = "en",
    reply_to: Optional[list] = None,
) -> None:
    """Render an email template pair and dispatch via the active backend.

    Args:
        template_base: e.g. "email/verify_email" -> renders
            "email/verify_email.html" and "email/verify_email.txt".
        context: rendered into both templates.
        to_email: single recipient.
        subject: email subject (already translated).
        language: BCP-47 code; activates Django translation context.
        reply_to: optional reply-to list.
    """
    with override(language):
        html_body = render_to_string(f"{template_base}.html", context)
        text_body = render_to_string(f"{template_base}.txt", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
        reply_to=reply_to or [settings.SUPPORT_EMAIL],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
    logger.info(
        "transactional email sent",
        extra={
            "template": template_base,
            "to": to_email,
            "language": language,
        },
    )


def send_verification_email(user, token: str, *, language: str = "en") -> None:
    """Email a user a link to verify their email address."""
    action_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    context = _build_context(user, action_url=action_url, token=token)
    _send(
        template_base="email/verify_email",
        context=context,
        to_email=user.email,
        subject=f"Verify your {settings.BRAND_NAME} email",
        language=language,
    )


def send_password_reset_email(user, token: str, *, language: str = "en") -> None:
    """Email a user a one-time password-reset link."""
    action_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    context = _build_context(user, action_url=action_url, token=token)
    _send(
        template_base="email/password_reset",
        context=context,
        to_email=user.email,
        subject=f"Reset your {settings.BRAND_NAME} password",
        language=language,
    )


def send_subscription_receipt(
    user, invoice_data: dict, *, language: str = "en"
) -> None:
    """Email a paid-invoice receipt with VAT breakdown.

    ``invoice_data`` keys (all str unless noted):
        plan_name             — e.g. "Plus"
        amount_display        — gross paid, e.g. "$24.00 EUR"
        subtotal_display      — pre-tax, e.g. "$20.00 EUR"
        tax_display           — VAT, e.g. "$4.00 EUR"; empty = no VAT
                                row rendered (B2B reverse-charge case)
        tax_rate_display      — label, e.g. "VAT 20%"; empty when no VAT
        period_start          — "YYYY-MM-DD"
        period_end            — "YYYY-MM-DD"
        date_paid_display     — "YYYY-MM-DD" or ""
        next_renewal_display  — "YYYY-MM-DD" or ""
        invoice_number        — Stripe invoice number ("INV-0042") or id
        hosted_invoice_url    — "View online" link
        invoice_pdf           — Stripe-hosted PDF download link

    The action button link in the email body uses hosted_invoice_url,
    falling back to invoice_pdf, then to the in-app billing page.
    """
    action_url = (
        invoice_data.get("hosted_invoice_url")
        or invoice_data.get("invoice_pdf")
        or f"{settings.FRONTEND_URL}/billing"
    )
    context = _build_context(user, invoice=invoice_data, action_url=action_url)
    _send(
        template_base="email/subscription_receipt",
        context=context,
        to_email=user.email,
        subject=f"Your {settings.BRAND_NAME} receipt",
        language=language,
    )


def send_subscription_canceled(
    user, *, language: str = "en", period_end: Optional[str] = None
) -> None:
    """Email a user that their subscription has been canceled."""
    action_url = f"{settings.FRONTEND_URL}/billing"
    invoice = {"period_end": period_end} if period_end else {}
    context = _build_context(user, action_url=action_url, invoice=invoice)
    _send(
        template_base="email/subscription_canceled",
        context=context,
        to_email=user.email,
        subject=f"Your {settings.BRAND_NAME} subscription has been canceled",
        language=language,
    )


def send_plan_change_email(
    user, from_plan, to_plan, *, language: str = "en"
) -> None:
    """Email a user that their subscription plan changed.

    ``from_plan`` may be ``None`` (first-time subscription); both
    ``from_plan`` and ``to_plan`` are ``SubscriptionPlan`` instances
    (or None) — only their display_name + name are read.
    """
    action_url = f"{settings.FRONTEND_URL}/pricing"
    is_first_subscription = from_plan is None
    context = _build_context(
        user,
        is_first_subscription=is_first_subscription,
        from_plan_name=(from_plan.display_name if from_plan else None),
        to_plan_name=to_plan.display_name,
        to_plan_slug=to_plan.name,
        action_url=action_url,
    )
    subject = (
        f"Welcome to {settings.BRAND_NAME} {to_plan.display_name}"
        if is_first_subscription
        else f"Your {settings.BRAND_NAME} plan changed to {to_plan.display_name}"
    )
    _send(
        template_base="email/plan_change",
        context=context,
        to_email=user.email,
        subject=subject,
        language=language,
    )


def send_account_deletion_confirmation(
    user,
    request_id: str = "",
    *,
    cancel_token: str = "",
    grace_days: int = 7,
    language: str = "en",
) -> None:
    """Email a user confirming their account-deletion request.

    ``cancel_token`` is the one-shot cancel JWT; when present the
    action link carries it so the (now logged-out, deactivated) user
    can cancel without authenticating. Falls back to a request-id
    lookup URL when absent.
    """
    if cancel_token:
        action_url = (
            f"{settings.FRONTEND_URL}/account/cancel-deletion"
            f"?token={cancel_token}"
        )
    else:
        action_url = (
            f"{settings.FRONTEND_URL}/account/cancel-deletion"
            f"?id={request_id}"
        )
    context = _build_context(
        user,
        request_id=request_id,
        grace_days=grace_days,
        action_url=action_url,
    )
    _send(
        template_base="email/account_deletion_confirmation",
        context=context,
        to_email=user.email,
        subject=f"Your {settings.BRAND_NAME} account deletion request",
        language=language,
    )


def send_data_export_ready_email(
    user, download_url: str, expires_at, *, language: str = "en"
) -> None:
    """Email a user that their GDPR data export is ready to download.

    ``download_url`` is the signed R2 URL; ``expires_at`` is the
    datetime the link stops working (rendered in the template).
    """
    context = _build_context(
        user, action_url=download_url, expires_at=expires_at
    )
    _send(
        template_base="email/data_export_ready",
        context=context,
        to_email=user.email,
        subject=f"Your {settings.BRAND_NAME} data export is ready",
        language=language,
    )


def send_account_deleted_email(
    to_email: str, full_name: str = "", *, language: str = "en"
) -> None:
    """Send the final account-deleted confirmation.

    The User row is already hard-deleted when this fires, so it takes
    the snapshot strings (email + full name) rather than a user
    instance; a minimal stand-in provides the ``get_short_name`` the
    shared templates expect.
    """
    short_name = (
        full_name.split()[0] if full_name else to_email.split("@")[0]
    )
    pseudo_user = SimpleNamespace(
        email=to_email,
        full_name=full_name,
        get_short_name=lambda: short_name,
    )
    context = _build_context(pseudo_user)
    _send(
        template_base="email/account_deleted",
        context=context,
        to_email=to_email,
        subject=(
            f"Your {settings.BRAND_NAME} account has been deleted"
        ),
        language=language,
    )


def send_subscription_payment_failed(
    user, *, language: str = "en"
) -> None:
    """Email a user that their latest invoice payment failed.

    Sent on ``invoice.payment_failed``. Stripe retries the charge
    automatically (default Smart Retries); if 3 attempts fail over 14
    days, Stripe cancels the subscription and the cancellation event
    handles the downgrade.
    """
    action_url = f"{settings.FRONTEND_URL}/settings/billing"
    context = _build_context(user, action_url=action_url)
    _send(
        template_base="email/subscription_payment_failed",
        context=context,
        to_email=user.email,
        subject=(
            f"Action required: payment failed for your "
            f"{settings.BRAND_NAME} subscription"
        ),
        language=language,
    )


def send_subscription_trial_ending(
    user, *, language: str = "en",
    trial_end: Optional[str] = None,
) -> None:
    """Email a user 3 days before their trial converts to paid.

    Fired by the ``customer.subscription.trial_will_end`` Stripe event
    (Stripe sends it 3 days before ``trial_end``; we don't compute the
    timing ourselves).
    """
    action_url = f"{settings.FRONTEND_URL}/settings/billing"
    context = _build_context(
        user, action_url=action_url, trial_end=trial_end,
    )
    _send(
        template_base="email/subscription_trial_ending",
        context=context,
        to_email=user.email,
        subject=f"Your {settings.BRAND_NAME} trial ends in 3 days",
        language=language,
    )
