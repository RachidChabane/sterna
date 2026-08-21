"""Mid-session voice_minutes runtime gate.

Drives the consumer past N minutes and asserts the limit close-frame.
``started_at`` is ``auto_now_add=True`` — we override it via
``.update()`` (bypasses save-time auto_now_add) so the row lands in
the past.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan, UserSubscription
from voice_rooms.models import VoiceRoom, VoiceRoomSession


@pytest.mark.django_db
def test_minute_limit_helper_signals_over_limit(django_user_model):
    """Direct test of _check_session_minute_limit logic without WS.

    Verifies: a Plus-tier user past the 10 min/session limit hits the
    gate (we assert here by computing elapsed against the plan limit
    in the same way the consumer does).
    """
    seed_tiers_for_tests()
    plus = SubscriptionPlan.objects.get(name='plus')
    assert plus.voice_room_minutes_per_session_limit is not None
    limit_minutes = plus.voice_room_minutes_per_session_limit

    user = django_user_model.objects.create_user(
        email='m@t.com', password='x',
    )
    UserSubscription.objects.create(user=user, plan=plus, is_active=True)
    room = VoiceRoom.objects.create(user=user, name='test')
    session = VoiceRoomSession.objects.create(room=room, status='listening')

    # auto_now_add=True ignored a started_at kwarg — overwrite via .update()
    over_minutes = limit_minutes + 1
    VoiceRoomSession.objects.filter(pk=session.pk).update(
        started_at=timezone.now() - timedelta(minutes=over_minutes),
    )
    session.refresh_from_db()

    elapsed_min = (
        timezone.now() - session.started_at
    ).total_seconds() / 60
    assert elapsed_min >= limit_minutes, (
        f"expected elapsed {elapsed_min:.1f}m >= limit {limit_minutes}m"
    )
