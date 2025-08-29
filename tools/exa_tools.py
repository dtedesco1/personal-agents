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

import os
from datetime import datetime, timedelta
from typing import Dict

from exa_py import Exa


def _exa_search(
    query: str,
    lookback_days: int,
    num_results: int,
    highlights: bool | Dict,
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
    exa: Exa = Exa(api_key=os.getenv("EXA_API_KEY"))
    results = exa.search_and_contents(
        query=query,
        type="auto",
        num_results=num_results,
        highlights=highlights,
        start_published_date=(
            datetime.now() - timedelta(days=lookback_days)
        ).isoformat(),
        text=fetch_fulltext,
    )
    return {"type": "exa", "results": [r.__dict__ for r in results.results]}


def exa_wide_search(query: str, lookback_days: int) -> dict:
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
        lookback_days: Number of days to look back from current date.
            Must be positive integer. Typical values: 1-30 days.
            Shorter periods for breaking news, longer for comprehensive analysis.

    Returns:
        Dictionary containing search results in standardized format:
        {
            "type": "exa",
            "results": [
                {
                    "title": "Article title",
                    "url": "https://example.com/article",
                    "published_date": "2024-01-15T10:00:00Z",
                    "score": 0.95,
                    "highlights": [
                        "First relevant highlight sentence...",
                        "Second relevant highlight sentence..."
                    ]
                }
            ]
        }

        Results are sorted by relevance score (highest first).
        Each result includes 2 highlights with up to 3 sentences each.

    Raises:
        ValueError: If query is empty or lookback_days is not positive.
        ExaAPIError: If the Exa API returns an error.
        ConnectionError: If unable to connect to Exa API.

    Example:
        >>> results = exa_wide_search("machine learning trends", 7)
        >>> print(f"Found {len(results['results'])} articles")
        >>> for article in results['results'][:3]:
        ...     print(f"- {article['title']}")
        ...     print(f"  {article['highlights'][0]}")

    Note:
        This function is designed for use by the WideSearchAgent. For detailed
        content analysis, use exa_deep_search instead.
    """
    results = _exa_search(
        query=query,
        lookback_days=lookback_days,
        num_results=30,
        highlights={"highlights_per_url": 2, "num_sentences": 3},
        fetch_fulltext=False,
    )
    return results


def exa_deep_search(query: str, lookback_days: int) -> dict:
    """
    Perform a deep search for focused, detailed content analysis.

    This function is optimized for in-depth analysis of specific topics.
    It returns 5 results with full text content to enable comprehensive
    analysis, fact-checking, and detailed understanding. Ideal for research,
    detailed reporting, and thorough topic investigation.

    Search Configuration:
        - Results: 5 articles maximum (optimized for context window limits)
        - Content: Full text of articles
        - Strategy: Depth over breadth
        - Use Case: Research, detailed analysis, fact verification

    Args:
        query: The search query string. Should be specific and focused
            for best results. Examples: "CRISPR gene editing ethics",
            "renewable energy storage solutions", "quantum entanglement applications".
        lookback_days: Number of days to look back from current date.
            Must be positive integer. Typical values: 7-90 days.
            Longer periods recommended for research topics with less frequent updates.

    Returns:
        Dictionary containing search results in standardized format:
        {
            "type": "exa",
            "results": [
                {
                    "title": "Article title",
                    "url": "https://example.com/article",
                    "published_date": "2024-01-15T10:00:00Z",
                    "score": 0.95,
                    "text": "Complete article text content..."
                }
            ]
        }

        Results are sorted by relevance score (highest first).
        Each result includes the complete article text for detailed analysis.

    Raises:
        ValueError: If query is empty or lookback_days is not positive.
        ExaAPIError: If the Exa API returns an error.
        ConnectionError: If unable to connect to Exa API.

    Example:
        >>> results = exa_deep_search("artificial general intelligence safety", 30)
        >>> print(f"Found {len(results['results'])} detailed articles")
        >>> for article in results['results']:
        ...     print(f"- {article['title']}")
        ...     print(f"  Content length: {len(article['text'])} characters")

    Note:
        This function is designed for use by the DeepSearchAgent.
        For broad topic coverage, use exa_wide_search instead.
        Full text content can be quite large - consider memory usage for batch processing.
    """
    results = _exa_search(
        query=query,
        lookback_days=lookback_days,
        num_results=5,
        highlights=False,
        fetch_fulltext=True,
    )
    return results
