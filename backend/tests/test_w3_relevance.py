"""W3: Exa news relevance gating — relevant / irrelevant / ambiguous / missing-ticker."""

from datetime import datetime, timezone
from typing import Optional

from app.collectors.exa import NewsItem
from app.collectors.relevance import filter_asset_relevant

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def _item(url: str, title: Optional[str], body: Optional[str]) -> NewsItem:
    return NewsItem(
        url=url, url_hash=None, title=title, body=body,
        published_at=NOW, author=None, source="example.com",
    )


def test_relevant_item_kept():
    """Full name or standalone ticker present -> relevant, kept."""
    items = [
        _item("u1", "Tencent 0700.HK beats Q3 estimates", "Quarterly profit up."),
        _item("u2", "What the 0700 rally means", None),
    ]
    kept, counts = filter_asset_relevant(
        items, name="Tencent", ticker="0700", provider_ticker="0700.HK",
    )
    assert [i.url for i in kept] == ["u1", "u2"]
    assert counts.relevant == 2
    assert counts.irrelevant_dropped == 0


def test_irrelevant_item_dropped():
    """No name, no ticker anywhere -> dropped and counted, never persisted."""
    items = [
        _item("u1", "Oil prices surge on OPEC output cuts", "Crude up 4%."),
        _item("u2", None, "A body about something completely unrelated."),
    ]
    kept, counts = filter_asset_relevant(
        items, name="Tencent", ticker="0700", provider_ticker="0700.HK",
    )
    assert kept == []
    assert counts.irrelevant_dropped == 2
    assert counts.relevant == 0


def test_ambiguous_item_kept_but_flagged():
    """Weak signal only -> kept, but counted as ambiguous so a reviewer can
    see why it survived.

    Two distinct weak signals:
    - the ticker '005930' appearing *embedded* inside a longer digit run
      ('0000593012') — not a standalone token;
    - only ONE word of a multi-word name ('Samsung' of 'Samsung
      Electronics') — a partial name hit, not the full phrase.
    """
    items = [
        _item("u1", "Ref 0000593012 confirmed by desk", None),
        _item("u2", "Samsung had a busy quarter", "Only one name word present."),
    ]
    kept, counts = filter_asset_relevant(
        items, name="Samsung Electronics", ticker="005930", provider_ticker="005930.KS",
    )
    assert [i.url for i in kept] == ["u1", "u2"]
    assert counts.ambiguous == 2
    assert counts.relevant == 0
    assert counts.irrelevant_dropped == 0


def test_missing_ticker_keeps_all_unfiltered():
    """No identifiers supplied at all -> nothing can be judged; every item
    is kept unfiltered and counted as no_ticker_kept."""
    items = [
        _item("u1", "Anything at all", "More text."),
        _item("u2", "Second article", None),
    ]
    kept, counts = filter_asset_relevant(items, name=None, ticker=None, provider_ticker=None)
    assert [i.url for i in kept] == ["u1", "u2"]
    assert counts.no_ticker_kept == 2
    assert counts.irrelevant_dropped == 0


def test_metadata_never_edited():
    """The filter must leave title/body/url/published_at/source untouched."""
    item = _item("u1", "Original title", "Original body")
    item.url_hash = "abc"
    kept, _ = filter_asset_relevant([item], name="Original", ticker=None, provider_ticker=None)
    assert kept[0] is item
    assert kept[0].title == "Original title"
    assert kept[0].body == "Original body"
    assert kept[0].url == "u1"
    assert kept[0].url_hash == "abc"
    assert kept[0].published_at == NOW


def test_provider_ticker_substring_is_exact_hit():
    """The provider ticker '0700.HK' appearing in the text is an exact hit."""
    items = [_item("u1", "Bulls add to 0700.HK", None)]
    kept, counts = filter_asset_relevant(
        items, name=None, ticker="0700", provider_ticker="0700.HK",
    )
    assert [i.url for i in kept] == ["u1"]
    assert counts.relevant == 1
