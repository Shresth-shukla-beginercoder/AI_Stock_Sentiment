"""Technical indicators from price history (Phase 8).

Look-back-only features: each indicator at time t uses only data strictly before t.
Missing values stay None (never forward-filled to 0). All inputs are sorted by
trade_date ascending; outputs preserve that order.

Indicators:
- Historical returns (1d, 5d, 10d)
- Moving averages (5d, 10d, 20d)
- Volatility (10d rolling std of returns)
- RSI (14-period)
- Volume indicators (volume MA, volume ratio)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import math


def historical_returns(
    prices: list[tuple[datetime, float]],
    *,
    periods: tuple[int, ...] = (1, 5, 10),
) -> list[dict[str, Optional[float]]]:
    """Calculate lagged returns for each period.

    Returns for period p at index i = (close[i] - close[i-p]) / close[i-p].
    Missing or insufficient history -> None.

    Args:
        prices: list of (trade_date, close) sorted ascending by date.
        periods: lookback periods for returns (default 1, 5, 10 days).

    Returns:
        List of dicts with keys f"return_{p}d" for each period, same length as prices.
    """
    n = len(prices)
    results: list[dict[str, Optional[float]]] = []

    for i in range(n):
        row: dict[str, Optional[float]] = {}
        current_close = prices[i][1]
        if current_close is None or current_close <= 0:
            # Cannot compute returns from missing/invalid close.
            for p in periods:
                row[f"return_{p}d"] = None
            results.append(row)
            continue

        for p in periods:
            if i < p:
                # Insufficient history for this period.
                row[f"return_{p}d"] = None
            else:
                past_close = prices[i - p][1]
                if past_close is None or past_close <= 0:
                    row[f"return_{p}d"] = None
                else:
                    row[f"return_{p}d"] = (current_close - past_close) / past_close

        results.append(row)

    return results


def moving_averages(
    prices: list[tuple[datetime, float]],
    *,
    windows: tuple[int, ...] = (5, 10, 20),
) -> list[dict[str, Optional[float]]]:
    """Calculate simple moving averages of close prices.

    MA at index i uses prices[i-window+1 : i+1]. Insufficient history -> None.

    Args:
        prices: list of (trade_date, close) sorted ascending.
        windows: MA window sizes (default 5, 10, 20 days).

    Returns:
        List of dicts with keys f"ma_{w}d", same length as prices.
    """
    n = len(prices)
    results: list[dict[str, Optional[float]]] = []

    for i in range(n):
        row: dict[str, Optional[float]] = {}
        for w in windows:
            if i < w - 1:
                # Need at least w observations.
                row[f"ma_{w}d"] = None
            else:
                window_prices = [prices[j][1] for j in range(i - w + 1, i + 1)]
                # Skip if any price in window is missing.
                if any(p is None or p <= 0 for p in window_prices):
                    row[f"ma_{w}d"] = None
                else:
                    row[f"ma_{w}d"] = sum(window_prices) / w

        results.append(row)

    return results


def volatility(
    prices: list[tuple[datetime, float]],
    *,
    window: int = 10,
) -> list[Optional[float]]:
    """Rolling standard deviation of daily returns (volatility proxy).

    At index i, compute std of returns over [i-window : i]. Insufficient data -> None.

    Args:
        prices: list of (trade_date, close) sorted ascending.
        window: rolling window size (default 10 days).

    Returns:
        List of volatility values (or None), same length as prices.
    """
    n = len(prices)
    results: list[Optional[float]] = []

    # First compute all daily returns.
    daily_returns: list[Optional[float]] = []
    for i in range(n):
        if i == 0:
            daily_returns.append(None)
        else:
            curr = prices[i][1]
            prev = prices[i - 1][1]
            if curr is None or prev is None or curr <= 0 or prev <= 0:
                daily_returns.append(None)
            else:
                daily_returns.append((curr - prev) / prev)

    # Rolling std of returns.
    for i in range(n):
        if i < window:
            # Need at least window+1 prices (window returns).
            results.append(None)
        else:
            window_returns = [daily_returns[j] for j in range(i - window + 1, i + 1)]
            if any(r is None for r in window_returns):
                results.append(None)
            else:
                mean_ret = sum(window_returns) / window
                variance = sum((r - mean_ret) ** 2 for r in window_returns) / window
                results.append(math.sqrt(variance))

    return results


def rsi(
    prices: list[tuple[datetime, float]],
    *,
    period: int = 14,
) -> list[Optional[float]]:
    """Relative Strength Index (14-period default).

    RSI = 100 - (100 / (1 + RS)), where RS = avg_gain / avg_loss over period.
    Insufficient history or zero avg_loss -> None (honest; no fabricated 100).

    Args:
        prices: list of (trade_date, close) sorted ascending.
        period: RSI period (default 14 days).

    Returns:
        List of RSI values (0-100 or None), same length as prices.
    """
    n = len(prices)
    results: list[Optional[float]] = []

    # Compute daily price changes.
    changes: list[Optional[float]] = []
    for i in range(n):
        if i == 0:
            changes.append(None)
        else:
            curr = prices[i][1]
            prev = prices[i - 1][1]
            if curr is None or prev is None or curr <= 0 or prev <= 0:
                changes.append(None)
            else:
                changes.append(curr - prev)

    # Rolling RSI computation.
    for i in range(n):
        if i < period:
            # Need period+1 prices (period changes).
            results.append(None)
        else:
            window_changes = [changes[j] for j in range(i - period + 1, i + 1)]
            if any(c is None for c in window_changes):
                results.append(None)
            else:
                gains = [c if c > 0 else 0.0 for c in window_changes]
                losses = [-c if c < 0 else 0.0 for c in window_changes]
                avg_gain = sum(gains) / period
                avg_loss = sum(losses) / period

                if avg_loss == 0:
                    # All gains or flat: RSI undefined (not 100).
                    results.append(None)
                else:
                    rs = avg_gain / avg_loss
                    rsi_val = 100.0 - (100.0 / (1.0 + rs))
                    results.append(rsi_val)

    return results


def volume_indicators(
    prices: list[tuple[datetime, float, Optional[int]]],
    *,
    ma_window: int = 10,
) -> list[dict[str, Optional[float]]]:
    """Volume-based indicators: volume MA and volume ratio.

    - volume_ma: rolling average of volume over ma_window days.
    - volume_ratio: current_volume / volume_ma (None if volume_ma is 0 or missing).

    Args:
        prices: list of (trade_date, close, volume) sorted ascending.
        ma_window: window for volume MA (default 10 days).

    Returns:
        List of dicts with keys "volume_ma", "volume_ratio", same length as prices.
    """
    n = len(prices)
    results: list[dict[str, Optional[float]]] = []

    for i in range(n):
        row: dict[str, Optional[float]] = {"volume_ma": None, "volume_ratio": None}
        current_vol = prices[i][2]

        if i < ma_window - 1:
            # Insufficient history.
            results.append(row)
            continue

        window_vols = [prices[j][2] for j in range(i - ma_window + 1, i + 1)]
        # Skip if any volume in window is missing.
        if any(v is None for v in window_vols):
            results.append(row)
            continue

        vol_ma = sum(window_vols) / ma_window
        row["volume_ma"] = vol_ma

        if current_vol is not None and vol_ma > 0:
            row["volume_ratio"] = current_vol / vol_ma

        results.append(row)

    return results
