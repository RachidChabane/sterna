"""Receipt email rendering integration tests (task 14).

These complement the notifications/tests/test_services.py tests by
exercising the *template output* directly with the exact invoice_data
shape that ``_handle_invoice_payment_succeeded`` builds.
"""

from types import SimpleNamespace

import pytest
from django.core import mail


def _make_user():
    user = SimpleNamespace(email='alice@t.com')
    user.get_short_name = lambda: 'Alice'
    user.full_name = 'Alice'
    return user


def _html_alternative(message):
    for content, mimetype in message.alternatives or []:
        if mimetype == 'text/html':
            return content
    return ''


@pytest.fixture
def receipt_settings(settings):
    settings.DEFAULT_FROM_EMAIL = 'noreply@example.com'
    settings.SUPPORT_EMAIL = 'support@example.com'
    settings.BRAND_NAME = 'Sterna'
    settings.FRONTEND_URL = 'http://testserver'
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    return settings


@pytest.fixture
def empty_outbox():
    mail.outbox = []
    yield
    mail.outbox = []


def test_with_vat_renders_vat_row(receipt_settings, empty_outbox):
    from notifications.services import send_subscription_receipt
    invoice = {
        'plan_name': 'Plus',
        'amount_display': '$23.80 EUR',
        'subtotal_display': '$20.00 EUR',
        'tax_display': '$3.80 EUR',
        'tax_rate_display': 'VAT 19%',
        'period_start': '2026-05-01',
        'period_end': '2026-06-01',
        'date_paid_display': '2026-05-01',
        'next_renewal_display': '2026-06-01',
        'invoice_number': 'INV-0042',
        'hosted_invoice_url': 'https://invoice.stripe.com/i/x',
        'invoice_pdf': 'https://invoice.stripe.com/p/x/pdf',
    }
    send_subscription_receipt(_make_user(), invoice)
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    html = _html_alternative(m)
    assert 'VAT 19%' in html
    assert '$3.80 EUR' in html
    assert '$20.00 EUR' in html
    assert '$23.80 EUR' in html
    assert 'https://invoice.stripe.com/i/x' in html
    assert 'https://invoice.stripe.com/p/x/pdf' in html


def test_without_vat_omits_vat_row(receipt_settings, empty_outbox):
    from notifications.services import send_subscription_receipt
    invoice = {
        'plan_name': 'Plus',
        'amount_display': '$20.00 EUR',
        'subtotal_display': '$20.00 EUR',
        'tax_display': '',  # reverse-charge B2B
        'tax_rate_display': '',
        'period_start': '2026-05-01',
        'period_end': '2026-06-01',
        'date_paid_display': '2026-05-01',
        'next_renewal_display': '2026-06-01',
        'invoice_number': 'INV-0042',
        'hosted_invoice_url': 'https://invoice.stripe.com/i/y',
        'invoice_pdf': 'https://invoice.stripe.com/p/y/pdf',
    }
    send_subscription_receipt(_make_user(), invoice)
    m = mail.outbox[0]
    html = _html_alternative(m)
    # No VAT label/amount rendered.
    assert 'VAT 19%' not in html
    assert '$3.80 EUR' not in html
    # Total + subtotal still present.
    assert '$20.00 EUR' in html
    # Both links still present.
    assert 'https://invoice.stripe.com/i/y' in html
    assert 'https://invoice.stripe.com/p/y/pdf' in html
