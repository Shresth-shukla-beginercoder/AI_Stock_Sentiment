"""End-to-end pipeline orchestration (Phase 9).

Coordinates the flow: collection → normalization → sentiment → features → training → predictions.
Reuses existing Phase 5-8 components. Ensures failed stages prevent downstream processing.
Preserves data provenance (is_demo, timestamps). Never generates fabricated results.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
import logging

from sqlalchemy.orm import Session

from app.database.models import Asset
from app.collectors.chain import market_provider_chain, fetch_daily_prices
from app.collectors.exa import ExaNewsCollector
from app.collectors.apify import ApifySocialCollector
from app.features.build_features import build_features, filter_for_training
from app.models.trainer import train_and_evaluate
from app.models.registry import register_model, persist_predictions
from app.services.persist import (
    persist_market_prices,
    persist_social,
    persist_news,
)
from app.core.logging import get_logger

# Late binding imports to avoid transformers circular dependency
# persist_sentiment_result will be imported inside stage_score_sentiment

_log = get_logger("services.orchestrate")


def _git_commit() -> str:
    """Real git HEAD SHA when this runs inside a checkout; 'no_git_repo' otherwise.

    Never invents a commit; the registry stores exactly what the environment
    reports so a model row can be reproduced against a real source state.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else "no_git_repo"
    except Exception:
        return "no_git_repo"


def _ml_seed() -> int:
    from app.core.config import get_settings
    return get_settings().ml_random_seed


def _ml_holdout_ratio() -> float:
    from app.core.config import get_settings
    return get_settings().ml_holdout_ratio


class PipelineStage:
    """Result of a pipeline stage execution."""

    def __init__(
        self,
        success: bool,
        stage_name: str,
        records_processed: int = 0,
        error: Optional[str] = None,
        data: Optional[dict] = None,
    ):
        self.success = success
        self.stage_name = stage_name
        self.records_processed = records_processed
        self.error = error
        self.data = data or {}

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"[{status}] {self.stage_name}: {self.records_processed} records" + (
            f" | error: {self.error}" if self.error else ""
        )


class EndToEndPipeline:
    """Orchestrates the full collection → prediction pipeline."""

    def __init__(self, session: Session):
        self.session = session
        self.stages = []

    def stage_collect_market_prices(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
    ) -> PipelineStage:
        """Collect market prices via the provider chain (primary + yfinance fallback)."""
        from app.core.config import get_settings

        try:
            if not asset or not asset.ticker:
                return PipelineStage(
                    success=False,
                    stage_name="collect_market",
                    error="Asset or ticker missing",
                )

            settings = get_settings()
            chain = market_provider_chain(
                settings, asset.ticker, start_date, end_date,
                exchange=asset.exchange,
            )
            provider, prices, attempts = fetch_daily_prices(chain)

            if not prices:
                _log.info(
                    "collect_market: no prices returned",
                    extra={"ticker": asset.ticker, "reason": "empty_result", "chain": attempts},
                )
                return PipelineStage(
                    success=True,
                    stage_name="collect_market",
                    records_processed=0,
                    data={"reason": "empty_result", "provider": provider.provider_name, "chain": attempts},
                )

            # Persist prices (handles deduplication via ON CONFLICT DO NOTHING),
            # attributed to the provider that actually produced the bars.
            persist_market_prices(self.session, asset.id, provider.provider_name, prices)

            _log.info(
                "collect_market: success",
                extra={"ticker": asset.ticker, "count": len(prices), "provider": provider.provider_name},
            )
            return PipelineStage(
                success=True,
                stage_name="collect_market",
                records_processed=len(prices),
                data={"provider": provider.provider_name, "chain": attempts},
            )

        except Exception as e:
            _log.error(
                "collect_market: failed",
                extra={"ticker": asset.ticker, "error": str(e)},
            )
            return PipelineStage(
                success=False,
                stage_name="collect_market",
                error=str(e),
            )

    def stage_collect_social(
        self,
        asset: Asset,
    ) -> PipelineStage:
        """Collect social posts via the exchange's CONFIGURED Apify Actors (W1).

        Mirrors the worker's collect:social path: actor refs come from
        settings (``apify_actor_*``), run inputs are built from each actor's
        own example/schema (never guessed), runs are bounded (wait / item cap
        / charge cap from settings), and normalized posts are persisted with
        ON CONFLICT DO NOTHING dedupe. Unconfigured platforms are reported,
        never filled with invented actors.
        """
        try:
            if not asset:
                return PipelineStage(
                    success=False,
                    stage_name="collect_social",
                    error="Asset missing",
                )

            from app.core.config import get_settings
            from app.collectors.exceptions import TransientError, RateLimitError
            from app.collectors.apify import resolve_exchange_actors

            settings = get_settings()
            collector = ApifySocialCollector(
                settings=settings,
                run_wait_seconds=settings.apify_run_wait_seconds,
            )
            records = resolve_exchange_actors(settings, asset.exchange, collector, asset.ticker)

            fetched = 0
            inserted = 0
            skipped = 0
            for rec in records:
                if not rec["configured"] or not rec["available"] or rec["run_input"] is None:
                    continue
                try:
                    run = collector.run_actor(
                        rec["actor"],
                        rec["run_input"],
                        wait=None,
                        max_items=settings.apify_run_max_items,
                        max_total_charge_usd=settings.apify_run_max_charge_usd,
                    )
                    raw = collector.fetch_items(run)
                    items = collector.to_social_items(raw, platform=rec["platform"])
                    if items:
                        res = persist_social(self.session, asset.id, items)
                        inserted += res.inserted
                        skipped += res.skipped_duplicates
                        fetched += len(items)
                except (TransientError, RateLimitError) as e:
                    rec["note"] = f"run failed ({type(e).__name__}): {e}"
                except Exception as e:
                    rec["note"] = f"run failed ({type(e).__name__}): {e}"

            if inserted:
                self.session.commit()

            # Honest short-circuit reason when nothing was persisted:
            # - no configured+available actor could run -> "actor_not_verified"
            # - available actor(s) ran but returned 0 usable posts -> "empty_result"
            # (both are success: the stage did its work and fabricated nothing.)
            data: dict = {"fetched": fetched, "inserted": inserted,
                          "skipped_duplicates": skipped, "actors": records}
            if fetched == 0:
                if any(r.get("available") and r.get("run_input") is not None for r in records):
                    data["reason"] = "empty_result"
                else:
                    data["reason"] = "actor_not_verified"

            _log.info(
                "collect_social: success",
                extra={"ticker": asset.ticker, "fetched": fetched, "inserted": inserted,
                       "actors": len(records)},
            )
            return PipelineStage(
                success=True,
                stage_name="collect_social",
                records_processed=inserted,
                data=data,
            )

        except Exception as e:
            _log.error("collect_social: failed", extra={"error": str(e)})
            return PipelineStage(
                success=False,
                stage_name="collect_social",
                error=str(e),
            )

    def stage_collect_news(
        self,
        asset: Asset,
        end_date: Optional[date] = None,
    ) -> PipelineStage:
        """Collect news articles via Exa (Phase 5), relevance-filtered (W3).

        The query includes the company name + ticker, the search is bounded to
        the configured lookback window, and items that do not mention the
        asset are dropped before persistence (``filter_asset_relevant``).
        """
        try:
            if not asset or not asset.ticker:
                return PipelineStage(
                    success=False,
                    stage_name="collect_news",
                    error="Asset or ticker missing",
                )

            from app.core.config import get_settings

            settings = get_settings()
            collector = ExaNewsCollector(settings=settings)
            query = f"{asset.name} {asset.ticker} news"
            items = collector.search(
                query,
                end=end_date,
                company_name=asset.name,
            )

            # W3: keep only articles that actually reference this asset.
            from app.collectors.relevance import filter_asset_relevant

            kept, rel = filter_asset_relevant(
                items,
                name=asset.name,
                ticker=asset.ticker,
                provider_ticker=asset.provider_ticker,
            )

            if not kept:
                _log.info(
                    "collect_news: nothing to persist",
                    extra={"ticker": asset.ticker, "fetched": len(items),
                           "dropped_irrelevant": rel.irrelevant_dropped,
                           "reason": "empty_result"},
                )
                return PipelineStage(
                    success=True,
                    stage_name="collect_news",
                    records_processed=0,
                    data={
                        "reason": "empty_result",
                        "fetched": len(items),
                        "relevance": {
                            "relevant": rel.relevant,
                            "ambiguous_kept": rel.ambiguous,
                            "irrelevant_dropped": rel.irrelevant_dropped,
                            "no_ticker_kept": rel.no_ticker_kept,
                            "total_in": rel.total_in,
                        },
                    },
                )

            res = persist_news(self.session, asset.id, kept)
            self.session.commit()

            _log.info(
                "collect_news: success",
                extra={"ticker": asset.ticker, "fetched": len(items),
                       "inserted": res.inserted},
            )
            return PipelineStage(
                success=True,
                stage_name="collect_news",
                records_processed=res.inserted,
                data={"fetched": len(items), "inserted": res.inserted,
                      "skipped_duplicates": res.skipped_duplicates,
                      "null_published_at": res.null_published_at,
                      "relevance": {
                          "relevant": rel.relevant,
                          "ambiguous_kept": rel.ambiguous,
                          "irrelevant_dropped": rel.irrelevant_dropped,
                          "no_ticker_kept": rel.no_ticker_kept,
                          "total_in": rel.total_in,
                      }},
            )

        except Exception as e:
            _log.error(
                "collect_news: failed",
                extra={"ticker": asset.ticker, "error": str(e)},
            )
            return PipelineStage(
                success=False,
                stage_name="collect_news",
                error=str(e),
            )

    def stage_score_sentiment(
        self,
        asset: Asset,
        trade_date: date,
        lookback_days: int = 10,
    ) -> PipelineStage:
        """Score sentiment for items in the rolling window (Phase 6).

        Real pipeline: preprocess → language routing → model select →
        ``analyze(text, model_id)`` → persist with ON CONFLICT DO NOTHING
        (idempotent per item+model). Items with no verified model for their
        language are counted as ``skipped_unroutable`` — never forced
        through an English model.
        """
        try:
            if not asset or not asset.id:
                return PipelineStage(
                    success=False,
                    stage_name="score_sentiment",
                    error="Asset missing",
                )

            window_start = trade_date - timedelta(days=lookback_days)

            from sqlalchemy import func, select
            from app.database.models import SocialPost, NewsArticle

            ts_social = func.coalesce(SocialPost.published_at, SocialPost.created_at)
            ts_news = func.coalesce(NewsArticle.published_at, NewsArticle.created_at)

            social_posts = self.session.execute(
                select(SocialPost).where(
                    SocialPost.asset_id == asset.id,
                    func.date(ts_social) >= window_start,
                    func.date(ts_social) <= trade_date,
                )
            ).scalars().all()

            news_articles = self.session.execute(
                select(NewsArticle).where(
                    NewsArticle.asset_id == asset.id,
                    func.date(ts_news) >= window_start,
                    func.date(ts_news) <= trade_date,
                )
            ).scalars().all()

            total_items = len(social_posts) + len(news_articles)
            if total_items == 0:
                _log.info(
                    "score_sentiment: no items to score",
                    extra={"ticker": asset.ticker, "date": trade_date},
                )
                return PipelineStage(
                    success=True,
                    stage_name="score_sentiment",
                    records_processed=0,
                    data={"reason": "no_items"},
                )

            # Real Phase 6 pipeline (late binding avoids the transformers
            # import at module load).
            from app.sentiment import (
                preprocess_for_sentiment,
                select_model,
                analyze,
                persist_sentiment_result,
            )

            scored = 0
            skipped_unroutable = 0
            duplicates = 0

            def _score_one(persist_type: str, route_type: str, item_id: int,
                           text: Optional[str]) -> None:
                nonlocal scored, skipped_unroutable, duplicates
                clean = preprocess_for_sentiment(text)
                if not clean:
                    skipped_unroutable += 1
                    return
                model_id = select_model(clean, route_type)
                if model_id is None:
                    # No verified model routes this language (e.g. CJK) —
                    # honestly skip rather than force an English model.
                    skipped_unroutable += 1
                    return
                result = analyze(clean, model_id)
                if result is None:
                    skipped_unroutable += 1
                    return
                res = persist_sentiment_result(
                    self.session,
                    item_type=persist_type,
                    item_id=item_id,
                    model_name=result.model_id,
                    label=result.label,
                    score=result.score,
                    p_pos=result.p_pos,
                    p_neu=result.p_neu,
                    p_neg=result.p_neg,
                )
                if res.inserted:
                    scored += 1
                else:
                    duplicates += 1

            for post in social_posts:
                _score_one("social_post", "social", post.id, post.content)
            for article in news_articles:
                _score_one("news_article", "news", article.id, article.body or article.title)

            if scored or duplicates:
                self.session.commit()
            _log.info(
                "score_sentiment: success",
                extra={"ticker": asset.ticker, "date": trade_date,
                       "scored": scored, "duplicates": duplicates,
                       "skipped_unroutable": skipped_unroutable},
            )
            return PipelineStage(
                success=True,
                stage_name="score_sentiment",
                records_processed=scored,
                data={"scored": scored, "duplicates": duplicates,
                      "skipped_unroutable": skipped_unroutable,
                      "total_items": total_items},
            )

        except Exception as e:
            _log.error(
                "score_sentiment: failed",
                extra={"ticker": asset.ticker, "error": str(e)},
            )
            return PipelineStage(
                success=False,
                stage_name="score_sentiment",
                error=str(e),
            )

    def stage_build_features(
        self,
        asset: Asset,
        lookback_days: int = 60,
    ) -> PipelineStage:
        """Build feature matrix from prices + sentiment (Phase 8)."""
        try:
            if not asset or not asset.id:
                return PipelineStage(
                    success=False,
                    stage_name="build_features",
                    error="Asset missing",
                )

            rows = build_features(self.session, asset.id, lookback_days=lookback_days)

            if not rows:
                _log.info(
                    "build_features: no rows generated",
                    extra={"ticker": asset.ticker},
                )
                return PipelineStage(
                    success=True,
                    stage_name="build_features",
                    records_processed=0,
                    data={"reason": "no_price_history"},
                )

            # Filter for training (remove rows without targets or experimental if needed)
            trainable_rows = filter_for_training(rows, require_target=True)

            if not trainable_rows:
                _log.info(
                    "build_features: no trainable rows after filtering",
                    extra={"ticker": asset.ticker, "total": len(rows)},
                )
                return PipelineStage(
                    success=True,
                    stage_name="build_features",
                    records_processed=0,
                    data={"reason": "no_targets", "total_rows": len(rows)},
                )

            _log.info(
                "build_features: success",
                extra={"ticker": asset.ticker, "rows": len(rows), "trainable": len(trainable_rows)},
            )
            return PipelineStage(
                success=True,
                stage_name="build_features",
                records_processed=len(trainable_rows),
                data={"rows": rows, "trainable_rows": trainable_rows},
            )

        except Exception as e:
            _log.error(
                "build_features: failed",
                extra={"ticker": asset.ticker, "error": str(e)},
            )
            return PipelineStage(
                success=False,
                stage_name="build_features",
                error=str(e),
            )

    def stage_train_model(
        self,
        asset: Asset,
        rows: list,
        model_version: str,
    ) -> PipelineStage:
        """Train model on feature rows (Phase 8)."""
        try:
            if not rows:
                return PipelineStage(
                    success=False,
                    stage_name="train_model",
                    error="No trainable rows",
                )

            registry_entry = train_and_evaluate(
                rows,
                model_version=model_version,
                git_commit=_git_commit(),  # real SHA when in a repo, else "no_git_repo"
                seed=_ml_seed(),
                holdout_ratio=_ml_holdout_ratio(),
            )

            if not registry_entry:
                return PipelineStage(
                    success=False,
                    stage_name="train_model",
                    error="Training returned no entry",
                )

            # Register model
            try:
                register_model(
                    self.session,
                    model_version=registry_entry["model_version"],
                    mae=registry_entry.get("mae"),
                    rmse=registry_entry.get("rmse"),
                    directional_accuracy=registry_entry.get("directional_accuracy"),
                    baseline_nochange_mae=registry_entry.get("baseline_nochange_mae"),
                    baseline_nochange_rmse=registry_entry.get("baseline_nochange_rmse"),
                    baseline_nochange_dir_acc=registry_entry.get("baseline_nochange_dir_acc"),
                    baseline_alwaysup_dir_acc=registry_entry.get("baseline_alwaysup_dir_acc"),
                    n_test=registry_entry.get("n_test"),
                    params=registry_entry.get("params"),
                    git_commit=registry_entry.get("git_commit"),
                    force=False,
                )
            except ValueError as e:
                # Model already exists
                _log.info(
                    "train_model: model version already registered",
                    extra={"model_version": model_version},
                )

            _log.info(
                "train_model: success",
                extra={
                    "ticker": asset.ticker,
                    "model_version": model_version,
                    "mae": registry_entry.get("mae"),
                    "n_test": registry_entry.get("n_test"),
                },
            )
            return PipelineStage(
                success=True,
                stage_name="train_model",
                records_processed=1,
                data={"registry_entry": registry_entry},
            )

        except Exception as e:
            _log.error(
                "train_model: failed",
                extra={"ticker": asset.ticker, "error": str(e)},
            )
            return PipelineStage(
                success=False,
                stage_name="train_model",
                error=str(e),
            )

    def stage_generate_predictions(
        self,
        asset: Asset,
        model_version: str,
        rows: list,
    ) -> PipelineStage:
        """Generate the next-TRADING-session prediction (W6).

        Uses ``predict_next_session``: the target is the row's actual next
        observed trading bar (never a calendar +1), and the predicted price is
        computed from that row's CLOSE (``close * (1 + return)``), never from
        a target-return value. Only one prediction is persisted — the one for
        the not-yet-traded next session — so a return value can never be
        mistaken for a price.
        """
        try:
            if not rows:
                return PipelineStage(
                    success=False,
                    stage_name="generate_predictions",
                    error="No rows",
                )

            from app.models.trainer import predict_next_session
            from app.features.make_target import predicted_price as _predicted_price

            pred = predict_next_session(rows, seed=_ml_seed())
            if pred is None:
                _log.info(
                    "generate_predictions: not enough history for an honest prediction",
                    extra={"ticker": asset.ticker},
                )
                return PipelineStage(
                    success=True,
                    stage_name="generate_predictions",
                    records_processed=0,
                    data={"reason": "insufficient_history"},
                )
            if pred["target_date"] is None:
                # No next observed trading bar exists — there is nothing to
                # predict for; report it instead of inventing a date.
                return PipelineStage(
                    success=True,
                    stage_name="generate_predictions",
                    records_processed=0,
                    data={"reason": "no_next_trading_session"},
                )

            # Self-check: predicted price must be the close basis, not a return.
            basis_close = pred["basis_close"]
            assert pred["predicted_price"] is None or (
                basis_close is not None
                and pred["predicted_price"] == _predicted_price(basis_close, pred["predicted_return"])
            ), "predicted price is not derived from the close basis"

            n = persist_predictions(
                self.session,
                asset.id,
                model_version,
                [{
                    "target_date": pred["target_date"],
                    "predicted_return": pred["predicted_return"],
                    "predicted_price": pred["predicted_price"],
                    "actual_close": None,  # backfilled by backfill_actual_closes
                    "experimental": pred["experimental"],
                }],
            )

            _log.info(
                "generate_predictions: success",
                extra={"ticker": asset.ticker, "model_version": model_version,
                       "target_date": pred["target_date"].isoformat(),
                       "experimental": pred["experimental"]},
            )
            return PipelineStage(
                success=True,
                stage_name="generate_predictions",
                records_processed=n,
                data={"target_date": pred["target_date"].isoformat(),
                      "predicted_return": pred["predicted_return"],
                      "predicted_price": pred["predicted_price"],
                      "experimental": pred["experimental"]},
            )

        except Exception as e:
            _log.error(
                "generate_predictions: failed",
                extra={"ticker": asset.ticker, "error": str(e)},
            )
            return PipelineStage(
                success=False,
                stage_name="generate_predictions",
                error=str(e),
            )

    def execute_full_pipeline(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
        model_version: str = "v0.1",
    ) -> dict:
        """Execute the full pipeline for one asset.

        Returns:
            Dict with stage results and summary.
        """
        results = {
            "asset": asset.ticker,
            "stages": [],
            "summary": None,
        }

        # Stage 1: Collect market prices
        stage1 = self.stage_collect_market_prices(asset, start_date, end_date)
        results["stages"].append(stage1)
        if not stage1.success:
            results["summary"] = "Pipeline halted: market price collection failed"
            return results

        # Stage 2: Collect social posts (config-driven Apify actors, W1)
        stage2 = self.stage_collect_social(asset)
        results["stages"].append(stage2)

        # Stage 3: Collect news
        stage3 = self.stage_collect_news(asset)
        results["stages"].append(stage3)

        # Stage 4: Score sentiment (for most recent date)
        most_recent_date = end_date
        stage4 = self.stage_score_sentiment(asset, most_recent_date)
        results["stages"].append(stage4)

        # Stage 5: Build features
        stage5 = self.stage_build_features(asset, lookback_days=60)
        results["stages"].append(stage5)
        if not stage5.success or not stage5.data.get("trainable_rows"):
            results["summary"] = "Pipeline halted: insufficient features for training"
            return results

        # Stage 6: Train model
        stage6 = self.stage_train_model(
            asset,
            stage5.data["trainable_rows"],
            model_version,
        )
        results["stages"].append(stage6)
        if not stage6.success:
            results["summary"] = "Pipeline halted: model training failed"
            return results

        # Stage 7: Generate predictions
        stage7 = self.stage_generate_predictions(
            asset,
            model_version,
            stage5.data["trainable_rows"],
        )
        results["stages"].append(stage7)

        results["summary"] = f"Pipeline complete: {len(results['stages'])} stages, {sum(1 for s in results['stages'] if s.success)} successful"
        return results
