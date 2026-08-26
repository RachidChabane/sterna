"""Web sources the frontend shows as citations for an answer.

Extractor. Two independent origins, both reduced to the same
``{"url", "title"}`` shape:

* search-tool results (Brave endpoints and ``fetch_web_page``), and
* markdown links the model wrote into its own answer.
"""

import logging
import re
from typing import Dict, List

from asgiref.sync import sync_to_async

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Cap on citations attached to one answer.
MAX_SOURCES_PER_MESSAGE = 20

BRAVE_TOOL_NAME_PREFIX = "brave_"
FETCH_WEB_PAGE_TOOL_NAME = "fetch_web_page"

MARKDOWN_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')

# Brave result-list keys that carry `{url, title}` items, each read
# independently of the others.
_URL_TITLE_RESULT_KEYS = ("news_results", "videos_results")


async def extract_web_sources(content: str) -> List[Dict[str, str]]:
    """Extract web sources from markdown links in content."""
    matches = MARKDOWN_LINK_RE.findall(content)
    if not matches:
        return []

    # Extract unique URLs, preserving first-seen order
    seen_urls = set()
    urls_to_fetch = []
    for _text, url in matches:
        if url not in seen_urls:
            urls_to_fetch.append(url)
            seen_urls.add(url)

    if not urls_to_fetch:
        return []

    logger.info(f"[LangChain] Extracted {len(urls_to_fetch)} unique URL(s) from markdown links")

    # Fetch titles in parallel (import here to avoid circular dependencies)
    from ..title_fetcher import fetch_titles_batch

    logger.info("[LangChain] Fetching page titles...")
    title_dict = await sync_to_async(fetch_titles_batch, thread_sensitive=False)(urls_to_fetch)

    web_sources = [{"url": url, "title": title_dict.get(url)} for url in urls_to_fetch]

    logger.info(f"[LangChain] Fetched {sum(1 for s in web_sources if s.get('title'))} title(s)")
    return web_sources


def _append_unique(sources, seen_urls, url, title) -> None:
    if url and url not in seen_urls:
        sources.append({"url": url, "title": title})
        seen_urls.add(url)


def _collect_from_brave_result(result: dict, sources: list, seen_urls: set) -> None:
    # Web results: "web_results" is only consulted when "results" is empty.
    for item in result.get("results", []) or result.get("web_results", []) or []:
        _append_unique(sources, seen_urls, item.get("url"), item.get("title", ""))

    for key in _URL_TITLE_RESULT_KEYS:
        for item in result.get(key, []) or []:
            _append_unique(sources, seen_urls, item.get("url"), item.get("title", ""))

    # Images results - use source URL
    for item in result.get("images_results", []) or []:
        _append_unique(
            sources, seen_urls, item.get("source") or item.get("url"), item.get("title", "")
        )

    infobox = result.get("infobox", {})
    if isinstance(infobox, dict):
        _append_unique(sources, seen_urls, infobox.get("url"), infobox.get("title", ""))

    # Locations (for local search)
    for item in result.get("locations", []) or []:
        _append_unique(
            sources, seen_urls, item.get("url"), item.get("name") or item.get("title", "")
        )


def extract_brave_search_sources(tool_results: List[Dict]) -> List[Dict[str, str]]:
    """
    Extract web sources from Brave Search tool results.

    Parses structured results from brave_web_search, brave_news_search,
    brave_image_search, brave_video_search, brave_local_search.
    """
    sources: List[Dict[str, str]] = []
    seen_urls: set[str] = set()

    for result_data in tool_results:
        tool_call = result_data.get("tool_call", {})
        tool_name = tool_call.get("function", {}).get("name", "")
        result = result_data.get("result", {})

        if tool_name == FETCH_WEB_PAGE_TOOL_NAME:
            if isinstance(result, dict) and result.get("success") and result.get("url"):
                _append_unique(sources, seen_urls, result["url"], result.get("title", ""))
            continue

        if not tool_name.startswith(BRAVE_TOOL_NAME_PREFIX):
            continue
        if not isinstance(result, dict) or not result.get("success", False):
            continue

        _collect_from_brave_result(result, sources, seen_urls)

    if sources:
        logger.info(f"[LangChain] Extracted {len(sources)} source(s) from Brave Search results")

    return sources[:MAX_SOURCES_PER_MESSAGE]
