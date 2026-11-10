"""Phase A1: historical market-price backfill (chunking + handler + dispatch).

DB-free unit tests for the chunk-window math, the ``backfill:market`` handler
(mocked provider chain + persistence), and dispatch registration/routing.
A single ``needs_db`` test exercises real persistence idempotency (gated off by
default, matching the rest of the worker suite).
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.collectors.chunking import iter_chunk_windows, trading_days_between
from app.collectors.provider import PriceRow
from app.database.models import CollectionJob

needs_db = pytest.mark.skipif(
    True, reason="requires real PostgreSQL; run with -m needs_db to override"
)


def _row(ticker: str, d: date, close: float) -> PriceRow:
    return PriceRow(
        ticker=ticker,
        trade_date=datetime(d.year, d.month, d.day, 16, 0, tzinfo=timezone.utc),
        open=close - 0.1,
        high=close + 0.2,
        low=close - 0.3,
        close=close,
        volume=1000,
    )


def _job(start: str, end: str, ticker: str = "0700", exchange: str = "HKEX") -> CollectionJob:
    return CollectionJob(
        dedupe_key=f"backfill:market:{ticker}:{start}:{end}",
        job_type="backfill:market",
        status="running",
        params={"asset_id": 1, "ticker": ticker, "exchange": exchange,
                "start": start, "end": end},
    )


# ============================================================================
# Chunk-window math (no DB)
# ============================================================================


def test_trading_days_between_counts_weekdays_only():
    # 2026-01-05 is a Monday; Mon..Fri = 5 weekdays, weekend dropped.
    days = trading_days_between(date(2026, 1, 5), date(2026, 1, 11))
    assert [d.isoformat() for d in days] == [
        "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
    ]


def test_trading_days_between_start_after_end_is_empty():
    assert trading_days_between(date(2026, 1, 9), date(2026, 1, 5)) == []


def test_chunking_no_trading_days_yields_no_chunks():
    # 2026-01-03 (Sat) .. 2026-01-04 (Sun): no weekdays -> no chunks.
    assert iter_chunk_windows(date(2026, 1, 3), date(2026, 1, 4), 60) == []


def test_chunking_exact_split_130_weekdays_at_cap_60():
    start = date(2026, 1, 5)  # a Monday
    # The 130th weekday on/after start:
    tdays = trading_days_between(start, start + timedelta(days=200))
    end = tdays[129]
    chunks = iter_chunk_windows(start, end, 60)
    sizes = [len(trading_days_between(cs, ce)) for cs, ce in chunks]
    assert sizes == [60, 60, 10]
    assert len(chunks) == 3


def test_chunking_invariants_preserve_every_trading_day():
    start, end, cap = date(2026, 1, 5), date(2026, 6, 30), 60
    chunks = iter_chunk_windows(start, end, cap)
    all_tdays = trading_days_between(start, end)
    assert len(all_tdays) > cap  # precondition: more than one chunk

    for cs, ce in chunks:
        assert cs <= ce
        assert len(trading_days_between(cs, ce)) <= cap

    assert chunks[0][0] == all_tdays[0]     # begins at the first trading day
    assert chunks[-1][1] == all_tdays[-1]    # ends at the last trading day

    reindexed = [d for cs, ce in chunks for d in trading_days_between(cs, ce)]
    assert reindexed == all_tdays             # no overlap, no gap


def test_chunking_rejects_bad_inputs():
    with pytest.raises(ValueError):
        iter_chunk_windows(date(2026, 1, 5), date(2026, 1, 5), 0)
    with pytest.raises(ValueError):
        iter_chunk_windows(date(2026, 1, 9), date(2026, 1, 5), 60)


# ============================================================================
# Dispatcher registration + routing
# ============================================================================


def test_dispatch_registers_backfill_market():
    from app.workers.dispatch import HANDLERS

    assert "backfill:market" in HANDLERS


def test_dispatch_job_runs_backfill_handler_end_to_end():
    from app.workers import dispatch
    from app.services.persist import PersistResult

    fake_provider = MagicMock()
    fake_provider.provider_name = "yfinance"
    rows = [_row("0700", date(2026, 5, 12), 1.05), _row("0700", date(2026, 5, 13), 1.15)]

    with patch("app.collectors.chain.market_provider_chain",
               return_value=[fake_provider]), \
         patch("app.collectors.chain.fetch_daily_prices",
               return_value=(fake_provider, rows, [{"provider": "yfinance", "ok": True, "rows": 2}])), \
         patch("app.collectors.retry.bounded_retry", side_effect=lambda f, settings=None: f()), \
         patch("app.services.persist.resolve_asset", return_value=MagicMock(id=7)), \
         patch("app.services.persist.persist_market_prices",
               return_value=PersistResult("yfinance", 2, 0)):
        out = dispatch.dispatch_job(MagicMock(), _job("2026-05-11", "2026-05-20"))

    assert out["provider"] == "yfinance"
    assert out["fetched"] == 2
    assert out["inserted"] == 2
    assert out["asset_resolved"] is True
    assert out["window"] == ["2026-05-11", "2026-05-20"]


def test_handle_backfill_market_builds_chunk_window_and_exchange():
    from app.workers import dispatch
    from app.services.persist import PersistResult

    fake_provider = MagicMock()
    fake_provider.provider_name = "yfinance"
    rows = [_row("0700", date(2026, 5, 12), 1.05)]

    with patch("app.collectors.chain.market_provider_chain") as m_chain, \
         patch("app.collectors.chain.fetch_daily_prices",
               return_value=(fake_provider, rows, [])), \
         patch("app.collectors.retry.bounded_retry", side_effect=lambda f, settings=None: f()), \
         patch("app.services.persist.resolve_asset", return_value=MagicMock(id=1)), \
         patch("app.services.persist.persist_market_prices",
               return_value=PersistResult("yfinance", 1, 0)) as m_persist:
        m_chain.return_value = [fake_provider]
        out = dispatch.handle_backfill_market(MagicMock(), _job("2026-05-11", "2026-05-20"))

    assert out["asset_resolved"] is True
    assert out["inserted"] == 1

    # chain built with the chunk window + exchange (positional start/end + exchange kwarg)
    a = m_chain.call_args.args
    assert a[1] == "0700"
    assert a[2] == date(2026, 5, 11)
    assert a[3] == date(2026, 5, 20)
    assert m_chain.call_args.kwargs["exchange"] == "HKEX"

    # persist called with (session, asset_id, provider, rows)
    pargs = m_persist.call_args.args
    assert pargs[1] == 1
    assert pargs[2] == "yfinance"
    assert len(pargs[3]) == 1


def test_handle_backfill_market_unresolved_asset_is_honest():
    from app.workers import dispatch

    fake_provider = MagicMock()
    fake_provider.provider_name = "yfinance"

    with patch("app.collectors.chain.market_provider_chain", return_value=[fake_provider]), \
         patch("app.collectors.chain.fetch_daily_prices",
               return_value=(fake_provider, [], [])), \
         patch("app.collectors.retry.bounded_retry", side_effect=lambda f, settings=None: f()), \
         patch("app.services.persist.resolve_asset", return_value=None), \
         patch("app.services.persist.persist_market_prices") as m_persist:
        out = dispatch.handle_backfill_market(MagicMock(), _job("2026-05-11", "2026-05-20"))

    assert out["asset_resolved"] is False
    assert out["inserted"] == 0
    m_persist.assert_not_called()


# ============================================================================
# Persistence idempotency (real DB, gated)
# ============================================================================


@needs_db
def test_backfill_persist_is_idempotent():
    from app.database.session import get_session_factory
    from app.services.persist import persist_market_prices

    factory = get_session_factory()
    rows = [_row("BKFL", date(2026, 5, 12), 1.05), _row("BKFL", date(2026, 5, 13), 1.15)]

    with factory() as s:
        # Reuse / a throwaway asset row is fine; we only assert the no-op semantics.
        res1 = persist_market_prices(s, 1, "yfinance", rows)
        res2 = persist_market_prices(s, 1, "yfinance", rows)
        s.commit()

    assert res1.inserted == 2
    assert res2.inserted == 0            # second identical write is a no-op
    assert res2.skipped_duplicates == 2
