"""Registry sanity tests.

Every feature_name has a registered FeatureSpec; flag_keys are valid
SubscriptionPlan.features keys; limit_fields exist on the model.
"""

from usage_quota.feature_registry import all_features
from usage_quota.models import SubscriptionPlan


VALID_FLAG_KEYS = {
    'chat',
    'search',
    'voice_rooms',
    'code_sessions',
    'knowledge_base',
    'image_gen',
    'video_gen',
    'sparks_view',
    'sparks_create',
    'mcp',
    'byok',
    'priority_coding_agent',
}


def test_every_feature_has_valid_flag():
    for name, spec in all_features().items():
        if spec.flag_key is None:
            continue
        assert spec.flag_key in VALID_FLAG_KEYS, (
            f"feature {name!r} has unknown flag_key {spec.flag_key!r}"
        )


def test_every_limit_field_exists_on_plan():
    plan_fields = {f.name for f in SubscriptionPlan._meta.get_fields()}
    for name, spec in all_features().items():
        if spec.limit_field is None:
            continue
        assert spec.limit_field in plan_fields, (
            f"feature {name!r} references missing field {spec.limit_field!r}"
        )


def test_units_are_known():
    for name, spec in all_features().items():
        assert spec.unit in {
            'count', 'seconds', 'mb', 'minutes_per_session',
        }, f"feature {name!r} has unknown unit {spec.unit!r}"


def test_quota_windows_are_known():
    for name, spec in all_features().items():
        assert spec.quota_window in {'weekly', 'session', 'storage'}, (
            f"feature {name!r} has unknown quota_window {spec.quota_window!r}"
        )
