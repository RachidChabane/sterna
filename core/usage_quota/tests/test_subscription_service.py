"""SubscriptionService.change_plan + admin endpoint tests."""
from unittest.mock import patch

import pytest
from django.utils import timezone

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan, UserSubscription
from usage_quota.services.subscription_service import SubscriptionService


@pytest.fixture
def seeded(db):
    seed_tiers_for_tests()


@pytest.mark.django_db
def test_upgrade_preserves_weekly_window(seeded, django_user_model):
    user = django_user_model.objects.create_user(email='u@t.com', password='x')
    free = SubscriptionPlan.objects.get(name='free')
    sub = UserSubscription.objects.create(
        user=user, plan=free, is_active=True,
    )
    sub.weekly_window_start = timezone.now()
    sub.save()
    window = sub.weekly_window_start

    SubscriptionService().change_plan(user, 'pro')

    sub.refresh_from_db()
    assert sub.plan.name == 'pro'
    assert sub.weekly_window_start == window


@pytest.mark.django_db
def test_downgrade_resets_session_window(seeded, django_user_model):
    user = django_user_model.objects.create_user(
        email='u2@t.com', password='x',
    )
    pro = SubscriptionPlan.objects.get(name='pro')
    sub = UserSubscription.objects.create(
        user=user, plan=pro, is_active=True,
    )
    sub.session_window_start = timezone.now()
    sub.weekly_window_start = timezone.now()
    sub.save()

    SubscriptionService().change_plan(user, 'free')

    sub.refresh_from_db()
    assert sub.plan.name == 'free'
    assert sub.session_window_start is None
    assert sub.weekly_window_start is not None  # preserved


@pytest.mark.django_db
def test_change_plan_writes_audit_log(seeded, django_user_model):
    """The ``_audit`` hook genuinely persists an AuditLog row (it used
    to fall into its warning fallback because ``AuditService.log_action``
    raised TypeError on a phantom ``project=`` kwarg)."""
    from audit_logging.models import AuditLog

    user = django_user_model.objects.create_user(
        email='audit@t.com', password='x',
    )
    free = SubscriptionPlan.objects.get(name='free')
    UserSubscription.objects.create(user=user, plan=free, is_active=True)

    SubscriptionService().change_plan(
        user, 'plus', initiated_by='admin', reason='ops request',
    )

    row = AuditLog.objects.get(action='subscription_plan_change')
    assert row.user_id == user.id
    assert row.success is True
    assert row.extra_data['from_plan'] == 'free'
    assert row.extra_data['to_plan'] == 'plus'
    assert row.extra_data['initiated_by'] == 'admin'
    assert row.extra_data['reason'] == 'ops request'


@pytest.mark.django_db
def test_same_plan_is_noop(seeded, django_user_model):
    user = django_user_model.objects.create_user(
        email='u3@t.com', password='x',
    )
    plus = SubscriptionPlan.objects.get(name='plus')
    UserSubscription.objects.create(user=user, plan=plus, is_active=True)
    with patch(
        'usage_quota.services.subscription_service.SubscriptionService._notify'
    ) as notify:
        result = SubscriptionService().change_plan(user, 'plus')
    notify.assert_not_called()
    assert result['from'] == 'plus'
    assert result['to'] == 'plus'


@pytest.mark.django_db
def test_first_time_subscription_creates_row(seeded, django_user_model):
    """When the user has no UserSubscription row yet, change_plan creates one."""
    user = django_user_model.objects.create_user(
        email='first@t.com', password='x',
    )
    assert not UserSubscription.objects.filter(user=user).exists()
    SubscriptionService().change_plan(user, 'plus')
    sub = UserSubscription.objects.get(user=user)
    assert sub.plan.name == 'plus'


@pytest.mark.django_db
def test_admin_endpoint_requires_staff(seeded, client, django_user_model):
    admin = django_user_model.objects.create_user(
        email='admin@t.com', password='x', is_staff=True,
    )
    user = django_user_model.objects.create_user(
        email='target@t.com', password='x',
    )
    UserSubscription.objects.create(
        user=user, plan=SubscriptionPlan.objects.get(name='free'),
    )
    client.force_login(admin)
    resp = client.put(
        f'/api/admin/users/{user.id}/plan/',
        data={'target_plan_slug': 'plus'},
        content_type='application/json',
    )
    assert resp.status_code == 200
    assert resp.json()['to'] == 'plus'


@pytest.mark.django_db
def test_admin_endpoint_blocks_non_staff(seeded, client, django_user_model):
    user = django_user_model.objects.create_user(
        email='reg@t.com', password='x',
    )
    client.force_login(user)
    resp = client.put(
        f'/api/admin/users/{user.id}/plan/',
        data={'target_plan_slug': 'plus'},
        content_type='application/json',
    )
    assert resp.status_code in (401, 403)
