"""
Brave Search Tools for LangChain

Provides advanced search capabilities using Brave Search API via dedicated service.

Usage tracking:
    The brave-search service handles quota checking and usage deduction internally.
    User context is passed via X-User-ID header, which is read from the
    BRAVE_SEARCH_USER_CONTEXT contextvars set by the caller (e.g., LangChain agent).
"""

from langchain.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from contextvars import ContextVar
import httpx
import logging
import json

logger = logging.getLogger(__name__)

# Context variable for passing user info to tools
# Set this before invoking tools that need user context for quota tracking
BRAVE_SEARCH_USER_CONTEXT: ContextVar[Optional[Dict[str, str]]] = ContextVar(
    'brave_search_user_context', default=None
)

# Brave Search service URL
BRAVE_SEARCH_SERVICE_URL = "http://brave-search:8004"

# Maximum text length for model (truncate long descriptions)
MAX_TEXT_LENGTH = 200


def truncate(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Truncate text to max length."""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length].rsplit(' ', 1)[0] + "..."


def condense_for_model(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Condense search results to reduce token usage.
    Keeps essential info for model reasoning, strips display-only metadata.
    """
    if not result.get("success", False):
        return result

    condensed = {
        "success": True,
        "query": result.get("query", ""),
        "result_count": result.get("result_count", 0)
    }

    # Condense web results
    if "results" in result or "web_results" in result:
        raw_results = result.get("web_results") or result.get("results", [])
        condensed["results"] = [
            {
                "title": r.get("title", ""),
                "description": truncate(r.get("description", "")),
                "url": r.get("url", "")
            }
            for r in raw_results[:7]  # Limit to top 7
        ]

    # Condense locations (keep minimal for model, frontend has full data)
    if "locations" in result and isinstance(result["locations"], list) and result["locations"]:
        condensed["locations"] = [
            {
                "title": loc.get("title", ""),
                "address": loc.get("address", ""),
                "rating": loc.get("rating")
            }
            for loc in result["locations"][:5]  # Limit to top 5
        ]

    # Condense infobox (keep just the summary)
    if "infobox" in result and result["infobox"]:
        ib = result["infobox"]
        condensed["infobox"] = {
            "title": ib.get("title", ""),
            "description": truncate(ib.get("description", ""), 300),
            "url": ib.get("url", "")
        }

    # Condense news
    if "news_results" in result and isinstance(result["news_results"], list) and result["news_results"]:
        condensed["news"] = [
            {
                "title": n.get("title", ""),
                "description": truncate(n.get("description", "")),
                "age": n.get("age", "")
            }
            for n in result["news_results"][:5]
        ]

    # Condense videos
    if "videos_results" in result and isinstance(result["videos_results"], list) and result["videos_results"]:
        condensed["videos"] = [
            {
                "title": v.get("title", ""),
                "description": truncate(v.get("description", ""), 100),
                "creator": v.get("creator", "")
            }
            for v in result["videos_results"][:5]
        ]

    # Condense FAQ (ensure it's a list before slicing)
    if "faq" in result and isinstance(result["faq"], list) and result["faq"]:
        condensed["faq"] = [
            {"q": f.get("question", ""), "a": truncate(f.get("answer", ""), 150)}
            for f in result["faq"][:3]
        ]

    # Condense discussions
    if "discussions" in result and isinstance(result["discussions"], list) and result["discussions"]:
        condensed["discussions"] = [
            {"title": d.get("title", ""), "forum": d.get("forum_name", "")}
            for d in result["discussions"][:3]
        ]

    return condensed


class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(..., description="Search query")
    count: Optional[int] = Field(10, description="Number of results (1-20)", ge=1, le=20)
    safesearch: Optional[Literal["off", "moderate", "strict"]] = Field("moderate", description="Safe search filter")
    freshness: Optional[Literal["pd", "pw", "pm", "py"]] = Field(None, description="pd=past day, pw=past week, pm=past month, py=past year")
    goggles_id: Optional[str] = Field(None, description="Goggles ID to filter search results with custom ranking")
    enriched: Optional[bool] = Field(False, description="Return enriched results with infobox, FAQ, discussions, locations, etc.")


class ImageSearchInput(BaseModel):
    """Input for image search tool."""
    query: str = Field(..., description="Search query for images")
    count: Optional[int] = Field(10, description="Number of results (1-150)", ge=1, le=150)
    safesearch: Optional[Literal["off", "strict"]] = Field("off", description="Safe search filter")


class LocalSearchInput(BaseModel):
    """Input for local/places search tool."""
    query: str = Field(..., description="Business or place name to search for")
    count: Optional[int] = Field(5, description="Number of results (1-20)", ge=1, le=20)


class VideoSearchInput(BaseModel):
    """Input for video search tool."""
    query: str = Field(..., description="Search query for videos")
    count: Optional[int] = Field(10, description="Number of results (1-20)", ge=1, le=20)
    safesearch: Optional[Literal["off", "strict"]] = Field("off", description="Safe search filter")


class NewsSearchInput(BaseModel):
    """Input for news search tool."""
    query: str = Field(..., description="Search query for news articles")
    count: Optional[int] = Field(10, description="Number of results (1-20)", ge=1, le=20)
    freshness: Optional[Literal["pd", "pw", "pm"]] = Field(None, description="pd=past day, pw=past week, pm=past month")


async def call_brave_search_service(endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call Brave Search service.

    Args:
        endpoint: API endpoint (e.g., 'search/web', 'search/images')
        data: Request payload

    Returns:
        Service response

    Note:
        User context for quota tracking is read from BRAVE_SEARCH_USER_CONTEXT.
        The brave-search service handles quota checking and deduction when
        X-User-ID header is provided.
    """
    url = f"{BRAVE_SEARCH_SERVICE_URL}/{endpoint}"

    # Build headers with user context for quota tracking
    headers = {"Content-Type": "application/json"}
    user_context = BRAVE_SEARCH_USER_CONTEXT.get()
    if user_context:
        if user_context.get("user_id"):
            headers["X-User-ID"] = user_context["user_id"]
        if user_context.get("authorization"):
            headers["Authorization"] = user_context["authorization"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        logger.error(f"[BraveSearchTool] Service error {e.response.status_code}: {e.response.text}")
        return {
            "success": False,
            "error": f"Brave Search service error: {e.response.text}",
            "results": [],
            "query": data.get("query", ""),
            "result_count": 0
        }
    except httpx.RequestError as e:
        logger.error(f"[BraveSearchTool] Request error: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to connect to Brave Search service: {str(e)}",
            "results": [],
            "query": data.get("query", ""),
            "result_count": 0
        }


@tool("brave_web_search", args_schema=WebSearchInput)
async def brave_web_search(
    query: str,
    count: int = 10,
    safesearch: str = "moderate",
    freshness: str = None,
    goggles_id: str = None,
    enriched: bool = False
) -> str:
    """Web search. enriched=True for entities/places (infobox, FAQ, map)."""
    logger.info(f"[BraveSearchTool] Web search: {query} (enriched={enriched}, goggles={goggles_id})")

    payload = {
        "query": query,
        "count": count,
        "safesearch": safesearch,
        "freshness": freshness if freshness else None,
        "goggles_id": goggles_id,
        "enriched": enriched
    }

    endpoint = "search/web/enriched" if enriched else "search/web"
    result = await call_brave_search_service(endpoint, payload)
    return json.dumps(result, ensure_ascii=False)


@tool("brave_image_search", args_schema=ImageSearchInput)
async def brave_image_search(
    query: str,
    count: int = 10,
    safesearch: str = "off"
) -> str:
    """Image search."""
    logger.info(f"[BraveSearchTool] Image search: {query}")

    payload = {
        "query": query,
        "count": count,
        "safesearch": safesearch
    }

    result = await call_brave_search_service("search/images", payload)
    return json.dumps(result, ensure_ascii=False)


@tool("brave_local_search", args_schema=LocalSearchInput)
async def brave_local_search(
    query: str,
    count: int = 5
) -> str:
    """Local business search (restaurants, shops, services)."""
    logger.info(f"[BraveSearchTool] Local search: {query}")

    payload = {
        "query": query,
        "count": count
    }

    result = await call_brave_search_service("search/local", payload)
    return json.dumps(result, ensure_ascii=False)


@tool("brave_video_search", args_schema=VideoSearchInput)
async def brave_video_search(
    query: str,
    count: int = 10,
    safesearch: str = "off"
) -> str:
    """Video search."""
    logger.info(f"[BraveSearchTool] Video search: {query}")

    payload = {
        "query": query,
        "count": count,
        "safesearch": safesearch
    }

    result = await call_brave_search_service("search/videos", payload)
    return json.dumps(result, ensure_ascii=False)


@tool("brave_news_search", args_schema=NewsSearchInput)
async def brave_news_search(
    query: str,
    count: int = 10,
    freshness: str = None
) -> str:
    """News article search."""
    logger.info(f"[BraveSearchTool] News search: {query}")

    payload = {
        "query": query,
        "count": count,
        "freshness": freshness if freshness else None
    }

    result = await call_brave_search_service("search/news", payload)
    return json.dumps(result, ensure_ascii=False)


# Export all tools
BRAVE_SEARCH_TOOLS = [
    brave_web_search,
    brave_image_search,
    brave_local_search,
    brave_video_search,
    brave_news_search
]

__all__ = [
    'BRAVE_SEARCH_TOOLS',
    'BRAVE_SEARCH_USER_CONTEXT',
    'brave_web_search',
    'brave_image_search',
    'brave_local_search',
    'brave_video_search',
    'brave_news_search',
]
