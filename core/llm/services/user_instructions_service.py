"""
User and chat instruction fetching for the streaming completion endpoint.
"""

import logging
import os

logger = logging.getLogger(__name__)


# Preference keys matching frontend settingsStore.ts
USER_INSTRUCTIONS_PREFERENCE_KEYS = {
    'ENABLED': 'settings.instructions.enabled',
    'CONTENT': 'settings.instructions.content',
}

USER_PREFERENCES_SERVICE_URL = os.environ.get(
    "USER_PREFERENCES_SERVICE_URL",
    "http://user-preferences:8000"
)


def get_user_instructions(user_id: str, auth_token: str) -> dict:
    """
    Fetch global user instructions settings from the user-preferences service.

    Returns:
        dict with keys: enabled (bool), content (str)
        Returns defaults if fetch fails or instructions are not set.
    """
    import httpx

    defaults = {
        'enabled': False,
        'content': '',
    }

    try:
        with httpx.Client(timeout=5.0) as client:
            # Fetch all settings-category preferences at once
            response = client.get(
                f"{USER_PREFERENCES_SERVICE_URL}/api/v1/preferences",
                params={'category': 'settings'},
                headers={'Authorization': f'Bearer {auth_token}'} if auth_token else {}
            )

            if response.status_code != 200:
                logger.debug(f"[UserInstructions] Failed to fetch preferences: {response.status_code}")
                return defaults

            data = response.json()
            prefs = data.get('preferences', {})

            # Extract instruction settings
            enabled = prefs.get(USER_INSTRUCTIONS_PREFERENCE_KEYS['ENABLED'], False)
            content = prefs.get(USER_INSTRUCTIONS_PREFERENCE_KEYS['CONTENT'], '')

            return {
                'enabled': bool(enabled),
                'content': content if isinstance(content, str) else '',
            }

    except Exception as e:
        logger.warning(f"[UserInstructions] Error fetching user instructions: {e}")
        return defaults


def get_chat_instructions(chat_id: str, user_id: str) -> dict:
    """
    Fetch chat-specific instructions from the database.

    Returns:
        dict with keys: content (str), mode (str: 'append'|'override')
        Returns empty dict if chat not found or has no instructions.
    """
    from conversations.models import Chat

    defaults = {
        'content': '',
        'mode': 'append',
    }

    if not chat_id:
        return defaults

    try:
        chat = Chat.objects.filter(
            id=chat_id,
            conversation__user_id=user_id
        ).first()

        if not chat or not chat.instructions:
            return defaults

        instructions = chat.instructions
        return {
            'content': instructions.get('content', ''),
            'mode': instructions.get('mode', 'append'),
        }

    except Exception as e:
        logger.warning(f"[ChatInstructions] Error fetching chat instructions: {e}")
        return defaults


