"""Import/export contract tests for app.collectors and worker dispatch (Phase 14).

Regression guard for the production ImportError:

    ImportError: cannot import name 'candidates_for' from 'app.collectors.apify'

Commit 7b181e1 (Phase 14a yfinance fallback) added `candidates_for` and
`EXCHANGE_PLATFORMS` to the app.collectors import/export block, but those
names were never defined in app/collectors/apify.py (they exist nowhere in
the repository). The fix removed the two ghost names; these tests pin the
contract so it cannot silently break again:

1. `import app.collectors` succeeds (previously raised ImportError).
2. Every name in `app.collectors.__all__` is an actual module attribute.
3. `import app.workers.dispatch` succeeds (it triggers the package import).
4. The apify candidate registry the social collector dispatch actually uses
   (CANDIDATE_ACTORS) keeps its shape.
"""

from __future__ import annotations

import importlib


def test_app_collectors_imports():
    app_collectors = importlib.import_module("app.collectors")
    assert app_collectors is not None


def test_app_collectors_all_names_resolvable():
    """Every advertised export must be a real attribute (catches ghost names)."""
    app_collectors = importlib.import_module("app.collectors")
    missing = [name for name in app_collectors.__all__ if not hasattr(app_collectors, name)]
    assert missing == [], f"names in __all__ not importable from app.collectors: {missing}"


def test_expected_public_names():
    """The names the rest of the backend actually consumes are all present."""
    app_collectors = importlib.import_module("app.collectors")
    for name in (
        "MarketDataProvider",
        "PriceRow",
        "TwelveDataProvider",
        "YfinanceDataProvider",
        "market_provider_chain",
        "fetch_daily_prices",
        "ExaNewsCollector",
        "NewsItem",
        "ApifySocialCollector",
        "ActorAvailability",
        "CandidateActor",
        "SocialPostItem",
        "CANDIDATE_ACTORS",
        "ProviderError",
    ):
        assert hasattr(app_collectors, name), f"missing public name: {name}"


def test_apify_submodule_imports():
    apify = importlib.import_module("app.collectors.apify")
    assert hasattr(apify, "ApifySocialCollector")
    assert hasattr(apify, "CANDIDATE_ACTORS")


def test_candidate_actors_registry_shape():
    """handle_collect_social iterates CANDIDATE_ACTORS; pin its shape."""
    app_collectors = importlib.import_module("app.collectors")
    candidates = app_collectors.CANDIDATE_ACTORS
    assert isinstance(candidates, tuple)
    assert len(candidates) == 2
    for candidate in candidates:
        assert isinstance(candidate, app_collectors.CandidateActor)
        assert candidate.ref  # "namespace/name"
        assert candidate.platform


def test_dispatch_module_imports():
    """Importing the dispatcher (production traceback site) must succeed."""
    dispatch = importlib.import_module("app.workers.dispatch")
    assert "collect:social" in dispatch.HANDLERS
    assert "collect:market" in dispatch.HANDLERS
    assert "collect:news" in dispatch.HANDLERS
    assert "score:sentiment" in dispatch.HANDLERS
