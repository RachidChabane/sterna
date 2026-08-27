"""
Web Fetch Tools for LangChain

Fetches web pages and returns LLM-optimized clean markdown.

Strategy (hybrid, best quality + resilience):
  1. Jina Reader API (r.jina.ai) — free, LLM-optimized, handles JS-rendered pages
  2. Trafilatura (local) — extracts main content, strips boilerplate
  3. Both strip navigation, ads, footers, cookie banners automatically
"""

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
import httpx
import json
import logging

logger = logging.getLogger(__name__)

# Limits
MAX_CONTENT_LENGTH = 64000  # Absolute max chars returned
DEFAULT_CONTENT_LENGTH = 5000
MAX_REDIRECTS = 5
MAX_LINKS = 50
JINA_TIMEOUT = 25.0
DIRECT_TIMEOUT = 20.0

# Jina Reader API — prepend to any URL for LLM-optimized markdown
JINA_READER_PREFIX = "https://r.jina.ai/"


async def _fetch_via_jina(url: str) -> Optional[dict]:
    """
    Fetch via Jina Reader API. Returns dict with content/title or None on failure.
    Jina handles: JS rendering, boilerplate removal, markdown conversion.
    """
    jina_url = f"{JINA_READER_PREFIX}{url}"

    try:
        async with httpx.AsyncClient(
            timeout=JINA_TIMEOUT,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
        ) as client:
            response = await client.get(
                jina_url,
                headers={
                    "Accept": "application/json",
                    "X-No-Cache": "true",
                },
            )
            response.raise_for_status()

            # Jina returns JSON when Accept: application/json
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError):
                # Fallback: Jina returned plain markdown text
                text = response.text.strip()
                if text and len(text) > 100:
                    return {
                        "content": text,
                        "title": None,
                        "description": None,
                        "url": url,
                    }
                return None

            content = data.get("data", {}).get("content") or data.get("content", "")
            if not content or len(content) < 50:
                return None

            return {
                "content": content,
                "title": data.get("data", {}).get("title") or data.get("title"),
                "description": data.get("data", {}).get("description") or data.get("description"),
                "url": data.get("data", {}).get("url") or url,
            }

    except Exception as e:
        logger.warning(f"[WebFetch] Jina Reader failed for {url}: {e}")
        return None


async def _fetch_via_trafilatura(url: str, extract_links: bool = False) -> Optional[dict]:
    """
    Fetch directly and extract main content with trafilatura.
    Strips boilerplate (nav, ads, footers), returns clean text/markdown.
    """
    try:
        # Fetch the page ourselves
        async with httpx.AsyncClient(
            timeout=DIRECT_TIMEOUT,
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            base_type = content_type.split(";")[0].strip().lower()

            # Non-HTML: return as-is
            if base_type == "application/json":
                try:
                    parsed = json.loads(response.text)
                    return {
                        "content": json.dumps(parsed, indent=2, ensure_ascii=False),
                        "title": None,
                        "description": None,
                        "url": str(response.url),
                        "content_type": "json",
                    }
                except json.JSONDecodeError:
                    pass

            if base_type not in ("text/html", "application/xhtml+xml", ""):
                # Plain text, XML, CSV, markdown — return directly
                text = response.text.strip()
                if text:
                    return {
                        "content": text,
                        "title": None,
                        "description": None,
                        "url": str(response.url),
                        "content_type": "text",
                    }
                return None

            html = response.text
            final_url = str(response.url)

        # Extract main content with trafilatura (runs sync, but fast)
        import trafilatura

        # Extract with markdown output
        content = trafilatura.extract(
            html,
            output_format="markdown",
            include_links=extract_links,
            include_tables=True,
            favor_recall=True,  # Prefer more content over precision
        )

        if not content or len(content) < 50:
            return None

        # Extract metadata
        metadata = trafilatura.extract_metadata(html)
        title = metadata.title if metadata else None
        description = metadata.description if metadata else None

        result: Dict[str, Any] = {
            "content": content,
            "title": title,
            "description": description,
            "url": final_url,
            "content_type": "markdown",
        }

        # Extract links if requested
        if extract_links:
            result["links"] = _extract_links_from_html(html)

        return result

    except Exception as e:
        logger.warning(f"[WebFetch] Trafilatura extraction failed for {url}: {e}")
        return None


def _extract_links_from_html(html: str) -> list:
    """Extract links from HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith(("http://", "https://")) and href not in seen:
                text = a.get_text(strip=True) or ""
                links.append({"url": href, "text": text[:100]})
                seen.add(href)
                if len(links) >= MAX_LINKS:
                    break
        return links
    except Exception:
        return []


def _smart_truncate(text: str, max_length: int) -> tuple:
    """Truncate text at paragraph or sentence boundary. Returns (text, was_truncated)."""
    if len(text) <= max_length:
        return text, False

    # Try to cut at paragraph boundary
    cut_point = text.rfind("\n\n", 0, max_length)
    if cut_point > max_length * 0.5:
        return text[:cut_point].rstrip() + "\n\n[... content truncated]", True

    # Try to cut at sentence boundary
    cut_point = max(
        text.rfind(". ", 0, max_length),
        text.rfind(".\n", 0, max_length),
        text.rfind("! ", 0, max_length),
        text.rfind("? ", 0, max_length),
    )
    if cut_point > max_length * 0.5:
        return text[:cut_point + 1].rstrip() + "\n\n[... content truncated]", True

    # Hard cut at word boundary
    cut_point = text.rfind(" ", 0, max_length)
    if cut_point > 0:
        return text[:cut_point].rstrip() + "\n\n[... content truncated]", True

    return text[:max_length] + "\n\n[... content truncated]", True


class FetchWebPageInput(BaseModel):
    """Input for fetch_web_page tool."""
    url: str = Field(..., description="Full URL to fetch (must start with http:// or https://)")
    max_length: Optional[int] = Field(
        DEFAULT_CONTENT_LENGTH,
        description=f"Maximum characters of content to return (max {MAX_CONTENT_LENGTH})",
        ge=1000,
        le=MAX_CONTENT_LENGTH,
    )
    extract_links: Optional[bool] = Field(
        False,
        description="Also return links found on the page"
    )


@tool("fetch_web_page", args_schema=FetchWebPageInput)
async def fetch_web_page(
    url: str,
    max_length: int = DEFAULT_CONTENT_LENGTH,
    extract_links: bool = False,
) -> str:
    """Fetch a web page and return its main content as clean markdown. Strips navigation, ads, and boilerplate. Use after web search to read full articles, documentation, or any page."""
    logger.info(f"[WebFetch] Fetching: {url}")

    # Validate URL
    if not url.startswith(("http://", "https://")):
        return json.dumps({
            "success": False,
            "error": "URL must start with http:// or https://",
            "url": url,
        })

    # Cap max_length
    max_length = min(max_length, MAX_CONTENT_LENGTH)

    # Strategy 1: Jina Reader API (best quality, handles JS)
    result_data = await _fetch_via_jina(url)
    source = "jina"

    # Strategy 2: Trafilatura fallback (local extraction)
    if not result_data:
        logger.info(f"[WebFetch] Jina failed, falling back to trafilatura for {url}")
        result_data = await _fetch_via_trafilatura(url, extract_links=extract_links)
        source = "trafilatura"

    if not result_data:
        return json.dumps({
            "success": False,
            "error": "Failed to fetch or extract content from page (both Jina and trafilatura failed)",
            "url": url,
        })

    content = result_data["content"]

    # Smart truncation
    content, was_truncated = _smart_truncate(content, max_length)

    result = {
        "success": True,
        "url": result_data.get("url", url),
        "content_type": result_data.get("content_type", "markdown"),
        "content": content,
        "truncated": was_truncated,
        "content_length": len(content),
    }

    if result_data.get("title"):
        result["title"] = result_data["title"]
    if result_data.get("description"):
        result["description"] = result_data["description"]
    if result_data.get("links"):
        result["links"] = result_data["links"]

    logger.info(f"[WebFetch] OK via {source}: {len(content)} chars, truncated={was_truncated}")
    return json.dumps(result, ensure_ascii=False)


# Export all tools
WEB_FETCH_TOOLS = [
    fetch_web_page,
]

__all__ = [
    "WEB_FETCH_TOOLS",
    "fetch_web_page",
]
