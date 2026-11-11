"""W6: predictions target the next TRADING session, prices derive from closes,
OOS holdout reporting is honest, and fixed seeds are deterministic."""

from datetime import date, timedelta

from app.features.build_features import FeatureRow
from app.features.make_target import predicted_price
from app.models.trainer import predict_next_session, train_and_evaluate

WEEK1 = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4),
         date(2026, 11, 5), date(2026, 11, 6)]
WEEK2 = [date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11),
         date(2026, 11, 12), date(2026, 11, 13)]
WEEK3 = [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18),
         date(2026, 11, 19), date(2026, 11, 20)]


def _weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _rows_for(dates: list[date], next_dates: list[date], *, last_has_target: bool = False) -> list[FeatureRow]:
    """Deterministic feature rows: close walk 100 + 2i, real next-session dates."""
    n = len(dates)
    closes = [100.0 + 2.0 * i for i in range(n)]
    rows = []
    for i, d in enumerate(dates):
        if i < n - 1:
            target = closes[i + 1] / closes[i] - 1.0
        elif last_has_target:
            target = 0.002  # fully observed/backfilled series
        else:
            target = None   # the honest "next session not yet observed" case
        rows.append(FeatureRow(
            asset_id=1,
            trade_date=d,
            return_1d=round(0.001 * i, 6),
            return_5d=round(0.002 * i, 6),
            return_10d=round(0.003 * i, 6),
            ma_5d=closes[i],
            ma_10d=closes[max(i - 4, 0)],
            ma_20d=closes[max(i - 19, 0)],
            volatility_10d=0.01 + 0.001 * (i % 3),
            rsi_14=50.0 + i,
            volume_ma=1000.0 + i,
            volume_ratio=1.0 + 0.01 * (i % 5),
            sentiment_social_score=(0.1 * i if i % 2 else None),
            sentiment_news_score=(-0.05 * i if i % 3 else None),
            target_return=target,
            close=closes[i],
            next_trade_date=next_dates[i] if i < len(next_dates) else None,
        ))
    return rows


def _predict_rows() -> list[FeatureRow]:
    dates = WEEK1 + WEEK2 + WEEK3  # 15 rows, last = Friday 2026-11-20
    nexts = dates[1:] + [date(2026, 11, 23)]  # Fri 11-20 -> Mon 11-23 (skips weekend)
    return _rows_for(dates, nexts)  # last row's target is None


def test_prediction_targets_next_trading_session_not_calendar_plus_one():
    rows = _predict_rows()
    assert rows[-1].target_return is None          # the next session is unobserved
    assert rows[-1].trade_date == date(2026, 11, 20)

    pred = predict_next_session(rows, seed=42)
    assert pred is not None
    # The target is the OBSERVED next trading session (Mon 11-23),
    # never a calendar-day +1 guess (Sat 11-21).
    assert pred["target_date"] == date(2026, 11, 23)
    assert pred["target_date"] != rows[-1].trade_date + timedelta(days=1)
    assert pred["made_from_trade_date"] == date(2026, 11, 20)


def test_predicted_price_derives_from_close_not_from_target():
    rows = _predict_rows()
    pred = predict_next_session(rows, seed=42)
    assert pred is not None
    assert pred["basis_close"] == rows[-1].close
    # W6 invariant: predicted_price = close * (1 + predicted_return),
    # i.e. it can never be a return value masquerading as a price.
    assert pred["predicted_price"] == predicted_price(pred["basis_close"], pred["predicted_return"])
    assert pred["predicted_price"] == pred["basis_close"] * (1.0 + pred["predicted_return"])
    assert pred["predicted_price"] > 1.0  # a price in the hundreds, not a ~0.01 return


def test_fixed_seed_is_deterministic():
    rows = _predict_rows()
    p1 = predict_next_session(rows, seed=42)
    p2 = predict_next_session(rows, seed=42)
    assert p1["predicted_return"] == p2["predicted_return"]
    assert p1["predicted_price"] == p2["predicted_price"]


def test_insufficient_history_is_honest_none():
    dates = WEEK1[:4] + WEEK2[:3]  # 7 rows -> only 6 realized targets (< 10)
    rows = _rows_for(dates, dates[1:])
    assert predict_next_session(rows, seed=42) is None


def test_oos_holdout_is_reported_honestly():
    dates = _weekdays(date(2026, 11, 2), 25)
    nexts = _weekdays(date(2026, 11, 2), 26)[1:]
    rows = _rows_for(dates, nexts, last_has_target=True)  # fully observed series

    entry = train_and_evaluate(
        rows, model_version="w6-test", git_commit="deadbeef",
        seed=42, holdout_ratio=0.2,
    )
    assert entry["git_commit"] == "deadbeef"
    assert entry["params"]["random_state"] == 42
    assert entry["params"]["holdout_ratio"] == 0.2
    # int(25 * 0.2) = 5 holdout rows, all with realized targets.
    assert entry["oos_n"] == 5
    assert entry["oos_mae"] is not None
    assert entry["oos_nochange_mae"] is not None
    # The beats-baseline flag must exactly mirror the OOS numbers —
    # the model is never "effective" if it loses to no-change.
    assert entry["beats_nochange_baseline"] == (entry["oos_mae"] < entry["oos_nochange_mae"])
    assert entry["params"]["oos_holdout"]["n"] == 5
    assert entry["params"]["oos_holdout"]["beats_nochange"] == entry["beats_nochange_baseline"]


def test_insufficient_oos_marks_experimental():
    dates = _weekdays(date(2026, 11, 2), 14)
    nexts = _weekdays(date(2026, 11, 2), 15)[1:]
    rows = _rows_for(dates, nexts, last_has_target=True)

    entry = train_and_evaluate(
        rows, model_version="w6-test", seed=42, holdout_ratio=0.2,
    )
    # int(14 * 0.2) = 2 holdout rows -> oos_n = 2 < 5 -> experimental.
    assert entry["oos_n"] == 2
    assert entry["experimental"] is True
