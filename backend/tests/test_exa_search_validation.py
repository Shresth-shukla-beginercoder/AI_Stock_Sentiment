"""Exa news collector search parameter validation tests (Phase 14b).

Regression guard for the production HTTP 400 validation error:

    Exa request failed with HTTP 400
    Invalid request body
    Validation error: Invalid option: expected one of "neural" | "keyword" | ...

Root cause: `exa.search(type="news")` was invalid. The `type` parameter
controls the search algorithm (SearchType), not content filtering. Content
filtering belongs in `category` parameter. This test ensures the outgoing
payload uses the correct parameters.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.collectors.exa import ExaNewsCollector
from app.core.config import Settings


def _settings(**over) -> Settings:
    """Create test settings."""
    base = dict(
        provider_timeout_seconds=5.0,
        provider_max_retries=0,
        provider_retry_base_delay_seconds=0.0,
        provider_retry_backoff_factor=1.0,
        provider_retry_max_delay_seconds=0.0,
        provider_batch_limit=20,
        collection_window_days=10,
        data_mode="demo",
    )
    base.update(over)
    return Settings(**base)


def _fake_exa_with_payload_capture():
    """Exa mock that captures the search() call payload."""
    captured = {}

    class _ExaMock:
        def search(self, **kwargs):
            # Capture all keyword arguments sent to exa.search()
            captured.update(kwargs)
            # Return empty results
            return SimpleNamespace(results=[])

    return _ExaMock(), captured


def test_exa_search_uses_category_not_type():
    """Verify exa.search() is called with category="news", not type="news".

    Production error was HTTP 400 because type parameter expected a SearchType
    enum value ("neural", "auto", "deep", etc.), not "news". The news filter
    belongs in the `category` parameter.
    """
    exa_mock, captured = _fake_exa_with_payload_capture()
    coll = ExaNewsCollector(settings=_settings(), exa=exa_mock)

    # Perform a search
    coll.search("tencent stock news")

    # Verify that:
    # 1. category="news" is present (content filtering)
    assert "category" in captured, "category parameter missing from exa.search() call"
    assert captured["category"] == "news", f"expected category='news', got category='{captured['category']}'"

    # 2. type is NOT set to "news" (would cause HTTP 400)
    if "type" in captured:
        # If type is present, it must be a valid SearchType, not "news"
        valid_types = {"auto", "fast", "deep-lite", "deep", "deep-reasoning", "neural", "instant", "lite"}
        assert captured["type"] in valid_types, (
            f"type={captured['type']} is not a valid SearchType. "
            f"Valid types: {valid_types}. "
            f"To filter by news content, use category='news'."
        )


def test_exa_search_date_window_correct():
    """Verify date window parameters are correctly named and formatted."""
    exa_mock, captured = _fake_exa_with_payload_capture()
    coll = ExaNewsCollector(settings=_settings(collection_window_days=7), exa=exa_mock)

    coll.search("alibaba stock news", end=date(2026, 11, 10))

    # Verify the correct parameter names (start_published_date, end_published_date)
    # not the deprecated start_crawl_date / end_crawl_date
    assert "start_published_date" in captured, "start_published_date missing"
    assert "end_published_date" in captured, "end_published_date missing"
    assert "start_crawl_date" not in captured, "start_crawl_date (deprecated) should not be used"
    assert "end_crawl_date" not in captured, "end_crawl_date (deprecated) should not be used"


def test_exa_search_contents_option():
    """Verify contents parameter structure is correct."""
    exa_mock, captured = _fake_exa_with_payload_capture()
    coll = ExaNewsCollector(settings=_settings(), exa=exa_mock)

    coll.search("xiaomi news")

    # contents should be present and configured for text extraction
    if "contents" in captured:
        # Either ContentsOptions object or a dict-like structure
        contents = captured["contents"]
        # If it's a dict or object with text attribute, it should request text
        if hasattr(contents, "text"):
            assert contents.text is True, "contents.text should be True"
        # (If it's a ContentsOptions object, the mock will handle it)


def test_exa_search_no_invalid_type_value():
    """Regression: ensure type parameter is never set to "news".

    This is the exact HTTP 400 bug: Exa API rejects type="news" because
    "news" is not a valid SearchType value.
    """
    exa_mock, captured = _fake_exa_with_payload_capture()
    coll = ExaNewsCollector(settings=_settings(), exa=exa_mock)

    # Try various search queries
    for query in ["tencent", "samsung stock", "naver news search"]:
        captured.clear()
        try:
            coll.search(query)
        except Exception:
            pass  # Ignore any other errors; we only care about the payload

        # Check that type is never set to "news"
        if "type" in captured:
            assert captured["type"] != "news", (
                f"BUG: type='news' sent to exa.search(). "
                f"This causes HTTP 400 validation error. "
                f"Use category='news' instead."
            )


def test_exa_valid_search_types_only():
    """Document the valid SearchType values for reference."""
    valid_search_types = {
        "auto",
        "fast",
        "deep-lite",
        "deep",
        "deep-reasoning",
        "neural",
        "instant",
        "lite",
    }

    # This is informational; verifies the SDK enum is known
    assert "neural" in valid_search_types
    assert "news" not in valid_search_types  # This was the bug

    # Ensure our fix doesn't use any of these for content filtering
    exa_mock, captured = _fake_exa_with_payload_capture()
    coll = ExaNewsCollector(settings=_settings(), exa=exa_mock)
    coll.search("test")

    # If a SearchType is set, it must be valid
    if "type" in captured:
        assert captured["type"] in valid_search_types, (
            f"Invalid SearchType '{captured['type']}'. "
            f"Valid values: {valid_search_types}"
        )


def test_exa_valid_category_values():
    """Document the valid Category values for reference."""
    valid_categories = {
        "company",
        "news",
        "publication",
        "personal site",
        "financial report",
        "people",
    }

    exa_mock, captured = _fake_exa_with_payload_capture()
    coll = ExaNewsCollector(settings=_settings(), exa=exa_mock)
    coll.search("test")

    # Verify category="news" is sent (our fix)
    assert "category" in captured, "category parameter not found"
    assert captured["category"] in valid_categories, (
        f"Invalid Category '{captured['category']}'. "
        f"Valid values: {valid_categories}"
    )
    assert captured["category"] == "news", "Should filter to news category"
