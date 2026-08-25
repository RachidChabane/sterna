"""
Knowledge Base Tools for LangChain

Provides RAG (Retrieval-Augmented Generation) capabilities by querying
the user's personal knowledge base.

Usage tracking:
    The knowledge_base service handles usage tracking internally.
    User context is passed via context variable.
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from contextvars import ContextVar
import logging

logger = logging.getLogger(__name__)

# Context variable for passing user info to tools
KNOWLEDGE_BASE_USER_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    'knowledge_base_user_context', default=None
)


class QueryKnowledgeBaseInput(BaseModel):
    """Input schema for query_knowledge_base tool."""
    query: str = Field(description="Natural language search query")
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of results to return (1-10)"
    )


@tool
def list_knowledge_base_documents() -> str:
    """
    List all documents in the user's personal knowledge base.

    Use this tool when the user wants to know what documents they have uploaded,
    asks "what's in my knowledge base?", or wants an overview of their documents.
    This does NOT search for content - it simply lists the available documents.

    For searching content within documents, use query_knowledge_base instead.

    Returns:
        A summary of all documents in the knowledge base with filenames, types, and sizes.
    """
    import json

    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available. Cannot access knowledge base."

    user = user_context.get('user')

    if not user:
        return "Error: User not authenticated. Cannot access knowledge base."

    try:
        from knowledge_base.models import KnowledgeDocument, KnowledgeBaseSettings

        # Check if knowledge base is enabled
        try:
            settings = KnowledgeBaseSettings.objects.get(user=user)
            if not settings.is_enabled:
                return "Your knowledge base is currently disabled. Enable it in the Knowledge Base settings."
        except KnowledgeBaseSettings.DoesNotExist:
            return "You haven't set up a knowledge base yet. Visit the Knowledge Base page to get started."

        # Get all documents for the user
        documents = KnowledgeDocument.objects.filter(user=user).order_by('-uploaded_at')

        if not documents.exists():
            return "Your knowledge base is empty. Upload documents through the Knowledge Base page to get started."

        # Format document list
        doc_list = []
        total_size = 0

        for doc in documents:
            size_kb = doc.file_size_bytes / 1024 if doc.file_size_bytes else 0
            total_size += doc.file_size_bytes or 0

            doc_info = {
                'filename': doc.filename,
                'type': doc.document_type,
                'size_kb': round(size_kb, 1),
                'status': doc.status,
                'uploaded_at': doc.uploaded_at.strftime('%Y-%m-%d %H:%M') if doc.uploaded_at else None,
                'chunk_count': doc.chunk_count or 0,
            }
            doc_list.append(doc_info)

        # Format for LLM
        formatted_lines = [f"📚 **Your Knowledge Base** ({len(doc_list)} document{'s' if len(doc_list) != 1 else ''}):\n"]

        for i, doc in enumerate(doc_list, 1):
            status_icon = "✅" if doc['status'] == 'ready' else "⏳" if doc['status'] == 'processing' else "❌"
            formatted_lines.append(
                f"{i}. {status_icon} **{doc['filename']}** ({doc['type'].upper()}, {doc['size_kb']:.1f} KB)"
            )

        total_size_mb = total_size / (1024 * 1024)
        formatted_lines.append(f"\n*Total size: {total_size_mb:.2f} MB*")

        return json.dumps({
            'total_documents': len(doc_list),
            'total_size_bytes': total_size,
            'documents': doc_list,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing knowledge base documents: {e}")
        return f"Error accessing knowledge base: {str(e)}"


@tool(args_schema=QueryKnowledgeBaseInput)
def query_knowledge_base(query: str, max_results: int = 5) -> str:
    """
    Search the user's personal knowledge base for relevant information.

    The knowledge base contains documents the user has uploaded (PDFs, Word docs,
    text files, etc.). Use this when the user asks about information that might
    be in their documents, mentions 'my notes', 'my documents', or uses @kb/@knowledge.

    Args:
        query: Natural language search query
        max_results: Maximum number of results to return (1-10)

    Returns:
        Relevant document excerpts with source information
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available. Cannot query knowledge base."

    user = user_context.get('user')
    conversation_id = user_context.get('conversation_id')
    chat_id = user_context.get('chat_id')

    if not user:
        return "Error: User not authenticated. Cannot query knowledge base."

    try:
        # Import here to avoid circular imports
        from knowledge_base.services import KnowledgeQueryService

        query_service = KnowledgeQueryService()
        results, log = query_service.search(
            user=user,
            query=query,
            max_results=max_results,
            conversation_id=conversation_id,
            chat_id=chat_id,
            invocation_type='auto' if not query.startswith('@') else 'explicit',
        )

        if not results:
            return f"No relevant documents found for query: '{query}'. The user's knowledge base may not contain information about this topic."

        # Format results for the LLM with structured data for frontend display
        import json

        structured_results = []
        formatted_parts = []

        for i, result in enumerate(results, 1):
            # Build structured result for frontend
            structured_results.append({
                'chunk_id': result.chunk_id,
                'document_id': result.document_id,
                'document_filename': result.document_filename,
                'document_type': result.document_type,
                'content': result.content[:500] + ('...' if len(result.content) > 500 else ''),  # Preview
                'full_content': result.content,  # Full content for LLM
                'chunk_index': result.chunk_index,
                'page_number': result.page_number,
                'similarity_score': result.similarity_score,
                'token_count': result.token_count,
            })

            # Format for LLM reading
            source_info = f"**Source: {result.document_filename}**"
            if result.page_number:
                source_info += f" (Page {result.page_number})"
            source_info += f" | Relevance: {result.similarity_score:.0%}"
            formatted_parts.append(f"{i}. {source_info}\n{result.content}")

        # Return JSON with both structured data (for frontend) and formatted text (for LLM)
        return json.dumps({
            'query': query,
            'total_results': len(results),
            'results': structured_results,
            'formatted_text': f"Found {len(results)} relevant excerpts from the user's knowledge base:\n\n" + "\n\n---\n\n".join(formatted_parts)
        })

    except Exception as e:
        logger.exception(f"Error querying knowledge base: {e}")
        return f"Error querying knowledge base: {str(e)}"


def get_knowledge_base_context_for_llm(
    user,
    query: str,
    max_results: int = 5,
    conversation_id: str = None,
    chat_id: str = None,
) -> Optional[str]:
    """
    Get knowledge base context to inject into LLM prompt.

    This is used for automatic knowledge base queries when the feature is enabled.

    Args:
        user: User object
        query: The user's message/query
        max_results: Maximum results to include
        conversation_id: Optional conversation ID for logging
        chat_id: Optional chat ID for logging

    Returns:
        Formatted context string or None if no relevant results
    """
    try:
        from knowledge_base.services import KnowledgeQueryService
        from knowledge_base.models import KnowledgeBaseSettings

        # Check if user has knowledge base enabled
        try:
            settings = KnowledgeBaseSettings.objects.get(user=user)
            if not settings.is_enabled or settings.total_documents == 0:
                return None
        except KnowledgeBaseSettings.DoesNotExist:
            return None

        query_service = KnowledgeQueryService()
        results, _ = query_service.search(
            user=user,
            query=query,
            max_results=max_results,
            conversation_id=conversation_id,
            chat_id=chat_id,
            invocation_type='auto',
        )

        if not results:
            return None

        return query_service.format_context_for_llm(results)

    except Exception as e:
        logger.exception(f"Error getting knowledge base context: {e}")
        return None


# All knowledge base tools
KNOWLEDGE_BASE_TOOLS = [
    list_knowledge_base_documents,  # List all documents (for "what's in my KB?" questions)
    query_knowledge_base,           # Semantic search within documents
]
