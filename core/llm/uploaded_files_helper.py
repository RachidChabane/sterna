"""
Helper to manage uploaded files in messages.

Usage in views.py:
    from llm.uploaded_files_helper import prepare_uploaded_files_context

    # When processing the message
    if message_has_attachments:
        files_context = prepare_uploaded_files_context(attachments, chat_id=chat_id)
        # Add files_context to system prompt or message
        # Files are automatically copied to /attachments_{chat_id}/ folder
"""

import base64
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def prepare_uploaded_files_context(attachments: List[Any], chat_id: Optional[str] = None) -> str:
    """
    Prepare context message to inform the model about available uploaded files.

    Args:
        attachments: List of uploaded files (Django objects with .name and .file)
        chat_id: Chat ID to construct the attachments folder path

    Returns:
        Context message to add to system prompt
    """
    if not attachments:
        return ""

    filenames = [att.name for att in attachments if hasattr(att, 'name')]

    if not filenames:
        return ""

    files_list = ", ".join(filenames)
    attachments_dir = f"/workspace/chat-{chat_id}/attachments" if chat_id else "attachments"

    return f"""📎 Uploaded files available ({len(filenames)}): {files_list}

**Location**: `{attachments_dir}/`

**How to use**:
- Read: `read_file('{attachments_dir}/{filenames[0]}')`
- List: `list_files('{attachments_dir}/')`

Files remain available throughout the conversation."""


def encode_uploaded_files(attachments: List[Any]) -> List[Dict[str, str]]:
    """
    Encode uploaded files to base64 for transmission to orchestrator.

    Args:
        attachments: List of uploaded files

    Returns:
        List of dicts with filename and content_base64
    """
    encoded_files = []

    for attachment in attachments:
        try:
            # Assume attachment has .name and .file or .read()
            filename = getattr(attachment, 'name', None)

            if not filename:
                logger.warning("Attachment without name, skipped")
                continue

            # Read content
            if hasattr(attachment, 'read'):
                content = attachment.read()
            elif hasattr(attachment, 'file'):
                content = attachment.file.read()
                # Reset file pointer after reading
                attachment.file.seek(0)
            else:
                logger.warning(f"Cannot read file {filename}")
                continue

            # Encode to base64
            content_base64 = base64.b64encode(content).decode('utf-8')

            encoded_files.append({
                "filename": filename,
                "content_base64": content_base64
            })

            logger.info(f"File encoded for upload: {filename} ({len(content)} bytes)")

        except Exception as e:
            logger.error(f"Error encoding file: {e}")
            continue

    return encoded_files


# Complete integration function
def prepare_message_with_uploaded_files(
    user_message: str,
    attachments: Optional[List[Any]] = None,
    chat_id: Optional[str] = None
) -> tuple[str, List[Dict[str, str]]]:
    """
    Prepare user message with uploaded files context.

    Args:
        user_message: Original user message
        attachments: Uploaded files (optional)
        chat_id: Chat ID for folder path

    Returns:
        Tuple (enriched_message, encoded_files)
        - enriched_message: Message with files context
        - encoded_files: List to pass to execute_code
    """
    if not attachments:
        return user_message, []

    files_context = prepare_uploaded_files_context(attachments, chat_id=chat_id)
    encoded_files = encode_uploaded_files(attachments)

    # Enrich message with context
    if files_context:
        enriched_message = f"{files_context}\n\n{user_message}"
    else:
        enriched_message = user_message

    return enriched_message, encoded_files
