"""Episode-2 regression guards for the integration fixes.

These tests are deliberately CI-safe: in-memory SQLite (no Neon) and a
mocked Hugging-Face pipeline (no model download). They lock in the four
defects found and fixed while taking the project to a verified end-to-end
state:

1. ``build_features`` must survive Postgres ``Numeric`` close values that
   arrive as ``decimal.Decimal`` (SQLAlchemy returns Decimal for Numeric
   columns on SQLite too). Without the float cast the indicator math
   (e.g. ``rsi``) raises ``TypeError: float + Decimal``.
2. ``analyzer.analyze`` must parse both transformers result shapes: the
   flat ``[{label, score}, ...]`` that transformers 5.x returns for a
   single string, and the nested ``[[{label, score}, ...]]`` from older
   versions / list inputs.
3. ``build_features`` sentiment-window filters must cast the DateTime
   column to SQLAlchemy's ``Date`` type engine (not the Python ``date``
   class, which SQLAlchemy cannot instantiate as a cast target).
4. The ``collect`` CLI's ``PersistResult`` attribute reference must be
   ``null_published_at`` (the real field), not the removed
   ``synthetic_timestamps``.
"""

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.models import Asset, MarketPrice


@pytest.fixture()
def sqlite_session():
    """In-memory SQLite with the full schema (Numeric -> Decimal on read)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        Base.metadata.create_all(conn)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


def test_build_features_survives_decimal_close(sqlite_session):
    """Regression: Decimal close (Postgres Numeric) must not crash indicators."""
    asset = Asset(exchange="HKEX", ticker="0700", provider_ticker="0700.HK")
    sqlite_session.add(asset)
    sqlite_session.flush()

    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    import math
    # Oscillating closes (gains AND losses) so RSI is defined for later rows;
    # a monotone series would leave avg_loss=0 and RSI=None.
    prices = [round(100.0 + 4.0 * math.sin(i / 2.0) + i * 0.05, 2) for i in range(30)]
    for i, close in enumerate(prices):
        sqlite_session.add(
            MarketPrice(
                asset_id=asset.id,
                provider="yfinance",
                trade_date=date(2026, 10, 1) + _timedelta_days(i),
                open=close,
                high=close,
                low=close,
                close=close,  # stored Numeric -> read back as Decimal
                volume=1000 + i,
                created_at=base,
            )
        )
    sqlite_session.commit()

    # Confirm the simulation: close reads back as Decimal (as on Postgres).
    one = sqlite_session.get(MarketPrice, sqlite_session.query(MarketPrice).first().id)
    assert isinstance(one.close, Decimal), "expected Decimal close from Numeric column"

    from app.features.build_features import build_features, filter_for_training

    rows = build_features(sqlite_session, asset.id, lookback_days=200)
    assert len(rows) == 30

    # Indicator outputs are plain floats (the float cast happened), not Decimal.
    with_ma = [r for r in rows if r.ma_5d is not None]
    assert with_ma, "expected some rows with a 5d moving average"
    assert isinstance(with_ma[-1].ma_5d, float)
    with_rsi = [r for r in rows if r.rsi_14 is not None]
    assert with_rsi, "expected some rows with RSI (would TypeError before the fix)"
    assert isinstance(with_rsi[-1].rsi_14, float)

    # A trainable subset exists and its features are usable.
    trainable = filter_for_training(rows, require_target=True)
    assert len(trainable) == 29


def _timedelta_days(n):
    from datetime import timedelta

    return timedelta(days=n)


def test_analyze_parses_flat_and_nested_results(monkeypatch):
    """Regression: transformers 5.x returns a flat list for a single string."""
    import app.sentiment.analyzer as az

    def make_pipe(result):
        class _Pipe:
            def __call__(self, text, **kwargs):
                # ``analyze`` passes truncation/max_length/return_all_scores/
                # top_k; the fake ignores them and just returns its canned
                # result so we can assert on the parsing path.
                return result
        return _Pipe()

    # transformers 5.x single-string shape: flat list of dicts.
    flat = [
        {"label": "positive", "score": 0.90},
        {"label": "neutral", "score": 0.09},
        {"label": "negative", "score": 0.01},
    ]
    monkeypatch.setattr(az, "_get_pipeline", lambda mid: make_pipe(flat))
    sc = az.analyze("Tencent posted record profit.", "cardiffnlp/x")
    assert sc is not None
    assert sc.label == "positive"
    assert sc.p_pos == pytest.approx(0.90, abs=0.01)
    assert sc.score == pytest.approx(0.89, abs=0.01)  # P(pos) - P(neg)

    # Older/list-input shape: nested list of dicts.
    nested = [[
        {"label": "negative", "score": 0.80},
        {"label": "neutral", "score": 0.15},
        {"label": "positive", "score": 0.05},
    ]]
    monkeypatch.setattr(az, "_get_pipeline", lambda mid: make_pipe(nested))
    sc2 = az.analyze("Alibaba faces a new crackdown.", "cardiffnlp/x")
    assert sc2 is not None
    assert sc2.label == "negative"
    assert sc2.p_neg == pytest.approx(0.80, abs=0.01)


def test_persist_result_exposes_null_published_at():
    """Regression guard for the collect.py CLI attribute contract."""
    from app.services.persist import persist_news, PersistResult

    res = persist_news(Mock(), asset_id=1, items=[])
    assert isinstance(res, PersistResult)
    assert hasattr(res, "null_published_at")
    assert not hasattr(res, "synthetic_timestamps"), (
        "collect CLI must reference res.null_published_at, not the removed field"
    )
