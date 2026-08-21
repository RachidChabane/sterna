"""Error handling and message translation for MCP connectors.

This module provides user-friendly error messages for different MCP connectors.
Each connector can have specific error patterns that are translated to clear,
actionable messages for end users.

Error mappings are loaded from JSON configuration files in the connectors/ directory.
This allows for easy modification of error messages without changing code.
"""

import json
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, List

logger = logging.getLogger(__name__)


def _load_connector_config(connector_slug: str) -> List[Dict]:
    """Load error mappings from JSON config file for a connector.

    Args:
        connector_slug: The slug of the connector (e.g., 'github', 'notion')

    Returns:
        List of error mapping dicts, or empty list if file not found
    """
    try:
        config_dir = Path(__file__).parent / "connectors"
        config_file = config_dir / f"{connector_slug}.json"

        if not config_file.exists():
            logger.debug(f"No JSON config found for connector '{connector_slug}' at {config_file}")
            return []

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if 'error_mappings' not in config:
            logger.warning(f"Config file for '{connector_slug}' missing 'error_mappings' key")
            return []

        return config['error_mappings']

    except Exception as e:
        logger.error(f"Error loading config for connector '{connector_slug}': {e}")
        return []


def _load_generic_config() -> List[Dict]:
    """Load generic error mappings from JSON config file.

    Returns:
        List of error mapping dicts, or empty list if file not found
    """
    try:
        config_dir = Path(__file__).parent / "connectors"
        config_file = config_dir / "generic.json"

        if not config_file.exists():
            logger.debug(f"No generic JSON config found at {config_file}")
            return []

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        if 'error_mappings' not in config:
            logger.warning("Generic config file missing 'error_mappings' key")
            return []

        return config['error_mappings']

    except Exception as e:
        logger.error(f"Error loading generic config: {e}")
        return []


# Default fallback mappings (used if JSON files are not available)
# These are kept for backward compatibility and as examples
DEFAULT_CONNECTOR_ERROR_MAPPINGS = {
    'github': [
        {
            'patterns': ['OAuth App access restrictions', 'access to third-parties is limited'],
            'user_message': 'Organization access restricted. An admin must approve this app in the GitHub organization settings.',
            'http_status': 'forbidden'
        },
        {
            'patterns': ['rate limit', 'API rate limit exceeded', 'rate_limit'],
            'user_message': 'GitHub API rate limit exceeded. Please try again later.',
            'http_status': 'rate_limit'
        },
        {
            'patterns': ['Bad credentials', 'Invalid authentication', 'authentication failed'],
            'user_message': 'GitHub authentication failed. Please reconnect your account.',
            'http_status': 'unauthorized'
        },
        {
            'patterns': ['Repository access blocked', 'suspended'],
            'user_message': 'Repository access blocked. Check repository permissions or account status.',
            'http_status': 'forbidden'
        },
    ],
    'notion': [
        # Notion-specific errors can be added here as we integrate Notion
        {
            'patterns': ['unauthorized', 'invalid_grant'],
            'user_message': 'Notion access denied. Please reconnect your Notion workspace.',
            'http_status': 'unauthorized'
        },
    ],
    'atlassian': [
        # Atlassian-specific errors can be added here as we integrate Jira/Confluence
        {
            'patterns': ['unauthorized', 'invalid_token'],
            'user_message': 'Atlassian access denied. Please reconnect your account.',
            'http_status': 'unauthorized'
        },
    ],
}

# Default generic error patterns (fallback when no connector-specific match is found)
DEFAULT_GENERIC_ERROR_MAPPINGS = [
    {
        'patterns': ['permission', 'forbidden', '403', 'access denied'],
        'user_message': 'Permission denied. Check your access rights for this resource.',
        'http_status': 'forbidden'
    },
    {
        'patterns': ['not found', '404', 'does not exist'],
        'user_message': 'Resource not found. Please check the repository or organization name.',
        'http_status': 'not_found'
    },
    {
        'patterns': ['unauthorized', '401', 'authentication'],
        'user_message': 'Authentication failed. Please reconnect your account.',
        'http_status': 'unauthorized'
    },
    {
        'patterns': ['timeout', 'timed out', 'deadline exceeded'],
        'user_message': 'Request timed out. The operation took too long. Please try again.',
        'http_status': 'timeout'
    },
    {
        'patterns': ['network', 'connection refused', 'connection failed'],
        'user_message': 'Network error. Please check your connection and try again.',
        'http_status': 'network_error'
    },
    {
        'patterns': ['invalid', 'malformed', 'bad request', '400'],
        'user_message': 'Invalid request. Please check the parameters and try again.',
        'http_status': 'bad_request'
    },
]


def get_user_friendly_error(error_msg: str, connector_slug: Optional[str] = None) -> Tuple[str, str]:
    """Transform a technical error message into a user-friendly message.

    This function first attempts to load error mappings from JSON configuration files.
    If JSON configs are not available, it falls back to hardcoded default mappings.

    Args:
        error_msg: The technical error message from the MCP server
        connector_slug: Optional connector slug (e.g., 'github', 'notion')

    Returns:
        Tuple of (user_message, http_status_category)
        - user_message: Clear, actionable message for the user
        - http_status_category: Category like 'forbidden', 'not_found', 'unauthorized', etc.
    """
    error_msg_lower = error_msg.lower()

    # Try connector-specific mappings first
    if connector_slug:
        # Try loading from JSON config first
        connector_mappings = _load_connector_config(connector_slug)

        # Fall back to default if no JSON config
        if not connector_mappings and connector_slug in DEFAULT_CONNECTOR_ERROR_MAPPINGS:
            connector_mappings = DEFAULT_CONNECTOR_ERROR_MAPPINGS[connector_slug]

        # Check patterns
        if connector_mappings:
            for mapping in connector_mappings:
                # Check if any pattern matches
                if any(pattern.lower() in error_msg_lower for pattern in mapping['patterns']):
                    return (mapping['user_message'], mapping['http_status'])

    # Fall back to generic mappings
    # Try loading from JSON config first
    generic_mappings = _load_generic_config()

    # Fall back to default if no JSON config
    if not generic_mappings:
        generic_mappings = DEFAULT_GENERIC_ERROR_MAPPINGS

    # Check patterns
    for mapping in generic_mappings:
        if any(pattern.lower() in error_msg_lower for pattern in mapping['patterns']):
            return (mapping['user_message'], mapping['http_status'])

    # If no pattern matches, return a generic message
    # Truncate very long errors to avoid overwhelming users
    if len(error_msg) > 200:
        return ('Tool execution failed. Please check the parameters and try again.', 'internal_error')

    # Return original message if it's reasonably short
    return (error_msg, 'internal_error')


def get_http_status_code(status_category: str) -> int:
    """Map a status category to an HTTP status code.

    Args:
        status_category: Category like 'forbidden', 'not_found', etc.

    Returns:
        HTTP status code (e.g., 403, 404, 500)
    """
    status_map = {
        'forbidden': 403,
        'unauthorized': 401,
        'not_found': 404,
        'bad_request': 400,
        'rate_limit': 429,
        'timeout': 504,
        'network_error': 503,
        'internal_error': 500,
    }

    return status_map.get(status_category, 500)
