"""
Optimized web page title fetcher.
Fetches only the first few KB of HTML to extract page titles quickly.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Cache for title fetching (simple in-memory cache)
# In production, consider using Redis for distributed caching
_title_cache: Dict[str, Optional[str]] = {}

# Configuration
MAX_FETCH_SIZE = 16 * 1024  # 16 KB should be enough to get <head> section
REQUEST_TIMEOUT = 3  # seconds
MAX_CONCURRENT_REQUESTS = 10


def fetch_title_single(url: str) -> tuple[str, Optional[str]]:
    """
    Fetch title for a single URL.

    Args:
        url: The URL to fetch

    Returns:
        Tuple of (url, title) where title is None if fetch failed
    """
    # Check cache first
    if url in _title_cache:
        logger.debug(f"[TITLE FETCH] Cache hit for {url}")
        return url, _title_cache[url]

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        # Use stream=True to read only partial content
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            stream=True
        )
        response.raise_for_status()

        # Read only first MAX_FETCH_SIZE bytes
        content = b''
        for chunk in response.iter_content(chunk_size=4096):
            content += chunk
            if len(content) >= MAX_FETCH_SIZE:
                break

        # Close the connection
        response.close()

        # Try to decode as UTF-8 (most common)
        try:
            html = content.decode('utf-8', errors='ignore')
        except Exception:
            html = content.decode('latin-1', errors='ignore')

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Try multiple methods to get title
        title = None

        # 1. Try <title> tag
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()

        # 2. Try og:title meta tag (often better formatted)
        if not title:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()

        # 3. Try twitter:title meta tag
        if not title:
            twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
            if twitter_title and twitter_title.get('content'):
                title = twitter_title['content'].strip()

        # Clean up title (remove extra whitespace, newlines)
        if title:
            title = re.sub(r'\s+', ' ', title).strip()
            # Limit title length
            if len(title) > 200:
                title = title[:197] + '...'

        # Cache the result
        _title_cache[url] = title

        logger.debug(f"[TITLE FETCH] Fetched title for {url}: {title}")
        return url, title

    except requests.Timeout:
        logger.warning(f"[TITLE FETCH] Timeout fetching {url}")
        _title_cache[url] = None
        return url, None
    except Exception as e:
        logger.warning(f"[TITLE FETCH] Error fetching {url}: {e}")
        _title_cache[url] = None
        return url, None


def fetch_titles_batch(urls: List[str]) -> Dict[str, Optional[str]]:
    """
    Fetch titles for multiple URLs in parallel using threads.

    Args:
        urls: List of URLs to fetch titles for

    Returns:
        Dictionary mapping URL to title (or None if fetch failed)
    """
    if not urls:
        return {}

    logger.info(f"[TITLE FETCH] Fetching titles for {len(urls)} URL(s)")

    # Filter out invalid URLs
    valid_urls = []
    for url in urls:
        try:
            parsed = urlparse(url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                valid_urls.append(url)
        except Exception:
            logger.warning(f"[TITLE FETCH] Invalid URL: {url}")

    if not valid_urls:
        return {}

    # Use ThreadPoolExecutor for parallel fetching
    title_dict = {}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        # Submit all tasks
        future_to_url = {executor.submit(fetch_title_single, url): url for url in valid_urls}

        # Collect results as they complete
        for future in as_completed(future_to_url):
            try:
                url, title = future.result()
                title_dict[url] = title
            except Exception as e:
                url = future_to_url[future]
                logger.error(f"[TITLE FETCH] Exception for {url}: {e}")
                title_dict[url] = None

    logger.info(f"[TITLE FETCH] Fetched {sum(1 for t in title_dict.values() if t)} title(s) successfully")
    return title_dict


def clear_cache():
    """Clear the title cache."""
    global _title_cache
    _title_cache.clear()
    logger.info("[TITLE FETCH] Cache cleared")
