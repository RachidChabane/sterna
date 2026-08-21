"""
Document Processing API Views

Provides endpoints for extracting text content from various document formats.
"""

import logging
import base64
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from llm.document_extractor import extract_document_content

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def extract_document(request):
    """
    Extract text content from a document file.

    Accepts a file upload (multipart/form-data) or base64-encoded file data (JSON).

    Request (multipart/form-data):
        - file: Document file (PDF, DOCX, XLSX, PPTX)

    Request (JSON):
        - filename: Name of the file
        - file_data: Base64-encoded file content
        - mime_type: Optional MIME type

    Response:
        {
            "success": true,
            "content": "Extracted text content...",
            "file_type": "pdf",
            "filename": "document.pdf",
            "character_count": 1234
        }

    or on error:
        {
            "success": false,
            "error": "Error message",
            "file_type": "pdf",
            "filename": "document.pdf"
        }
    """
    try:
        # Handle multipart/form-data (file upload)
        if request.FILES:
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return Response(
                    {'success': False, 'error': 'No file provided'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            filename = uploaded_file.name
            file_data = uploaded_file.read()
            mime_type = uploaded_file.content_type

        # Handle JSON with base64-encoded data
        elif request.content_type == 'application/json':
            data = request.data
            filename = data.get('filename')
            file_data_b64 = data.get('file_data')
            mime_type = data.get('mime_type')

            if not filename or not file_data_b64:
                return Response(
                    {'success': False, 'error': 'Missing filename or file_data'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Decode base64 data
            try:
                # Handle data URI scheme (data:mime/type;base64,...)
                if file_data_b64.startswith('data:'):
                    # Extract base64 part after the comma
                    file_data_b64 = file_data_b64.split(',', 1)[1]

                file_data = base64.b64decode(file_data_b64)
            except Exception as e:
                return Response(
                    {'success': False, 'error': f'Invalid base64 data: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        else:
            return Response(
                {'success': False, 'error': 'Unsupported content type. Use multipart/form-data or application/json'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract content
        result = extract_document_content(file_data, filename, mime_type)

        if result['success']:
            response_data = {
                'success': True,
                'content': result['content'],
                'file_type': result['file_type'],
                'filename': filename,
                'character_count': len(result['content']) if result['content'] else 0
            }
            logger.info(f"Successfully extracted content from {filename}: {response_data['character_count']} characters")
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            response_data = {
                'success': False,
                'error': result['error'],
                'file_type': result['file_type'],
                'filename': filename
            }
            logger.warning(f"Failed to extract content from {filename}: {result['error']}")
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Document extraction endpoint error: {error_msg}", exc_info=True)
        return Response(
            {'success': False, 'error': f'Server error: {error_msg}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
