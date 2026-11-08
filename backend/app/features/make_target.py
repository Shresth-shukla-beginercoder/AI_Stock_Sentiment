"""Next-day-return target construction (Phase 8).

Target = (close[t+1] / close[t]) - 1 for the next trading day.
Predicted price = last_close * (1 + predicted_return).

This module is **read-only**: it does not modify data, only computes targets
for a given lookback window. Targets are never included in feature matrices
(no look-ahead bias).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def compute_targets(
    asset_id: int,
    prices: list[tuple[date, float]],  # (trade_date, close)
) -> dict[date, Optional[float]]:
    """Compute next-day return targets.

    For each date t, target = (close[t+1] / close[t]) - 1.
    The target at date t requires close[t+1], so the last date has no target.

    Args:
        asset_id: Asset ID (for logging/identification only).
        prices: List of (trade_date, close) sorted ascending by date.

    Returns:
        Dict mapping trade_date -> next_day_return (or None if no next day).
    """
    targets: dict[date, Optional[float]] = {}

    for i in range(len(prices) - 1):
        current_date, current_close = prices[i]
        next_date, next_close = prices[i + 1]

        if current_close is None or current_close <= 0 or next_close is None or next_close <= 0:
            targets[current_date] = None
        else:
            targets[current_date] = (next_close / current_close) - 1.0

    # Last date has no next-day target.
    if prices:
        last_date, last_close = prices[-1]
        targets[last_date] = None

    return targets


def predicted_price(
    last_close: float,
    predicted_return: Optional[float],
) -> Optional[float]:
    """Compute predicted price from predicted return.

    predicted_price = last_close * (1 + predicted_return).
    If predicted_return is None or last_close <= 0, returns None.

    Args:
        last_close: The most recent close price.
        predicted_return: Model's predicted next-day return.

    Returns:
        Predicted close price, or None if inputs are invalid.
    """
    if predicted_return is None or last_close is None or last_close <= 0:
        return None
    return last_close * (1.0 + predicted_return)
