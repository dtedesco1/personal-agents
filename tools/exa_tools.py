"""
Exa API integration tools for web search functionality.

This module provides tools for interacting with the Exa API to perform web searches
with different strategies and configurations. It includes both wide search (broad
coverage) and deep search (detailed content) capabilities.

Key Functions:
    - exa_wide_search: Broad search with highlights (30 results)
    - exa_deep_search: Focused search with full text (10 results)
    - _exa_search: Internal utility function (not for direct agent use)

Search Strategies:
    - Wide Search: Optimized for comprehensive topic coverage
    - Deep Search: Optimized for detailed content analysis

Configuration:
    - API Key: Set EXA_API_KEY environment variable
    - Search Type: "auto" for automatic query interpretation
    - Date Filtering: Configurable lookback period
    - Content Types: Highlights vs full text

Usage:
    from underlines_adk.tools.exa_tools import exa_wide_search, exa_deep_search

    # Wide search for comprehensive coverage
    results = exa_wide_search("AI news", lookback_days=7)

    # Deep search for detailed analysis
    detailed = exa_deep_search("specific topic", lookback_days=30)

Return Format:
    {
        "type": "exa",
        "results": [
            {
                "title": "Article title",
                "url": "https://example.com",
                "highlights": ["highlight1", "highlight2"],  # Wide search
                "text": "Full article text...",                # Deep search
                "published_date": "2024-01-15T10:00:00Z",
                "score": 0.95
            }
        ]
    }

Dependencies:
    - exa-py: Official Exa API client
    - Standard library: os, datetime, typing

Environment Variables:
    - EXA_API_KEY: Required for API access
"""
# Export ToolSpec for generic server auto-registration
from mcp_servers.tooling import ToolSpec


import os
from datetime import datetime, timedelta


def _exa_search(
    query: str,
    lookback_days: int,
    num_results: int,
    highlights: dict | bool,
    fetch_fulltext: bool,
) -> dict:
    """
    Internal utility function for Exa API searches.

    This is a low-level function that handles the actual API communication with Exa.
    It should not be used directly by agents - use exa_wide_search or exa_deep_search
    instead, which provide appropriate configurations for different search strategies.

    The function handles API key retrieval, date filtering, and result formatting
    in a consistent manner across all search types.

    Args:
        query: The search query string to send to Exa API.
        lookback_days: Number of days to look back from current date for results.
            Must be positive integer. Used to filter recent content.
        num_results: Maximum number of results to return. Exa API limits apply.
        highlights: Either boolean or dict specifying highlight configuration.
            If dict, should contain 'highlights_per_url' and 'num_sentences'.
            If False, no highlights are fetched.
        fetch_fulltext: Whether to fetch full article text content.
            If True, includes complete article text in results.
            If False, only metadata and highlights (if requested) are included.

    Returns:
        Dictionary with standardized format:
        {
            "type": "exa",
            "results": [
                {
                    "title": str,
                    "url": str,
                    "published_date": str,
                    "score": float,
                    "highlights": List[str] (if highlights requested),
                    "text": str (if fetch_fulltext=True)
                }
            ]
        }

    Raises:
        ValueError: If EXA_API_KEY environment variable is not set.
        ExaAPIError: If the Exa API returns an error response.
        ConnectionError: If unable to connect to Exa API.

    Note:
        This function is internal to the tools module. Agents should use the
        specialized wrapper functions (exa_wide_search, exa_deep_search) which
        provide appropriate configurations for different use cases.
    """
    # Resolve and validate API key (server loads .env at startup)
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        raise ValueError("Missing EXA_API_KEY environment variable for Exa API access.")

    # Defensive validation for lookback_days (>=1)
    try:
        lookback_days_int = int(lookback_days)
        if lookback_days_int <= 0:
            raise ValueError
    except Exception:
        raise ValueError("lookback_days must be a positive integer (>=1).")

    # Lazy import here to avoid forcing exa-py dependency during server startup
    try:
        from exa_py import Exa  # type: ignore
    except Exception as e:  # ImportError or pkg not available
        raise RuntimeError(
            "exa-py is not installed. To use Exa tools, install it in your environment.\n"
            "Options:\n"
            "- Use a project venv: pip install exa-py\n"
            "- Or run via uvx adding --with exa-py\n"
            "- Or add exa-py to your dev environment where OpenCode runs\n"
            "Also set EXA_API_KEY in the environment before calling these tools."
        ) from e

    exa: Exa = Exa(api_key=api_key)
    kwargs: dict = {
        "query": query,
        "type": "auto",
        "num_results": num_results,
        "start_published_date": (datetime.now() - timedelta(days=lookback_days_int)).isoformat(),
    }
    # Exa expects True or an options object for these fields; omit to disable
    if fetch_fulltext:
        kwargs["text"] = True
    if isinstance(highlights, dict):
        kwargs["highlights"] = highlights
    elif highlights is True:
        kwargs["highlights"] = True

    results = exa.search_and_contents(**kwargs)
    return {"type": "exa", "results": [r.__dict__ for r in results.results]}


def exa_wide_search(query: str, lookback_days: int | None) -> dict:
    """
    Perform a wide search for comprehensive topic coverage.

    This function is optimized for gathering broad information about a topic.
    It returns 30 results with highlights to provide comprehensive coverage
    while keeping response sizes manageable. Ideal for initial topic exploration
    and gathering diverse perspectives.

    Search Configuration:
        - Results: 30 articles maximum
        - Content: Highlights only (2 per URL, 3 sentences each)
        - Strategy: Breadth over depth
        - Use Case: Topic exploration, news gathering, trend analysis

    Args:
        query: The search query string. Should be descriptive and specific
            enough to get relevant results. Examples: "artificial intelligence news",
            "climate change policy 2024", "quantum computing breakthroughs".
        lookback_days: Optional number of days to look back from current date.
            If None, defaults to EXA_DEFAULT_LOOKBACK_DAYS (env) or 3.

    Returns:
        Dictionary containing search results in standardized format.
    """
    # Resolve default lookback if not provided
    if lookback_days is None:
        from os import getenv
        try:
            lookback_days = int(getenv("EXA_DEFAULT_LOOKBACK_DAYS", "3"))
        except Exception:
            lookback_days = 3

    results = _exa_search(
        query=query,
        lookback_days=lookback_days,
        num_results=30,
        highlights={"highlights_per_url": 2, "num_sentences": 3},
        fetch_fulltext=False,
    )
    return results


def exa_deep_search(query: str, lookback_days: int | None) -> dict:
    """
    Perform a deep search for focused, detailed content analysis.

    Args:
        query: The search query string.
        lookback_days: Optional number of days; if None uses EXA_DEFAULT_LOOKBACK_DAYS (env) or 3.

    Returns:
        Dictionary containing search results in standardized format.
    """
    if lookback_days is None:
        from os import getenv
        try:
            lookback_days = int(getenv("EXA_DEFAULT_LOOKBACK_DAYS", "3"))
        except Exception:
            lookback_days = 3

    results = _exa_search(
        query=query,
        lookback_days=lookback_days,
        num_results=5,
        highlights=False,
        fetch_fulltext=True,
    )
    return results


# Register via TOOL_SPECS for the generic server
TOOL_SPECS = [
    ToolSpec(func=exa_wide_search, name="wide_search", annotations={"title": "Exa Wide Search", "readOnlyHint": True}),
    ToolSpec(func=exa_deep_search, name="deep_search", annotations={"title": "Exa Deep Search", "readOnlyHint": True}),
]
