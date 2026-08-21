from typing import Literal

ReleaseStage = Literal['ga', 'beta', 'experimental', 'hidden']

FEATURE_RELEASE_STAGE: dict[str, ReleaseStage] = {
    'spark_deploy': 'beta',
    'knowledge_base': 'beta',
    'coding_agent': 'beta',
    'mcp_local': 'beta',
    'mcp_remote': 'hidden',
    'video_generation': 'beta',
}

# Stages visible to non-admin users
_PUBLIC_STAGES: set[ReleaseStage] = {'ga', 'beta', 'experimental', 'preview'}


def get_release_stages(is_admin: bool = False) -> dict[str, ReleaseStage]:
    """Return stage map filtered for the caller's permission level."""
    if is_admin:
        return dict(FEATURE_RELEASE_STAGE)
    return {k: v for k, v in FEATURE_RELEASE_STAGE.items() if v in _PUBLIC_STAGES}
