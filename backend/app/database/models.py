"""SQLAlchemy 2.0 models for all eight tables.

Schema is created ONLY by Alembic migrations (never create_all in production).
Data rules (CLAUDE.md):
- UTC everywhere (UTCDateTime rejects naive timestamps).
- No data means None/NULL, never 0.
- Dedupe keys use SHA-256 content hashes + ON CONFLICT DO NOTHING at write time.
- No usernames are stored; source identifiers and content hashes are kept.

Eight tables:
  assets, social_posts, news_articles, market_prices,
  sentiment_results, predictions, model_evaluations, collection_jobs
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database.base import Base, UTCDateTime, utc_now, _server_ts


class JSONColumn(TypeDecorator):
    """Portable JSON: JSONB on PostgreSQL, JSON elsewhere (tests)."""

    impl = JSON
    cache_ok = True
    cache_key = "jsoncol"

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


# ---------------------------------------------------------------------------
# 1. assets — configurable, holds the provider ticker mapping.
# ---------------------------------------------------------------------------
class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("exchange", "ticker", name="uq_assets_exchange_ticker"),
        Index("ix_assets_exchange", "exchange"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)  # e.g. HKEX / KRX
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_ticker: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider_symbol_format: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    market_data_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Tickers remain pending confirmation; this flag records that.
    # DB-side defaults keep raw SQL (bypassing the ORM) consistent with the ORM.
    confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now, server_default=_server_ts()
    )

    social_posts: Mapped[list["SocialPost"]] = relationship(
        "SocialPost", back_populates="asset", cascade="all, delete-orphan"
    )
    news_articles: Mapped[list["NewsArticle"]] = relationship(
        "NewsArticle", back_populates="asset", cascade="all, delete-orphan"
    )
    market_prices: Mapped[list["MarketPrice"]] = relationship(
        "MarketPrice", back_populates="asset", cascade="all, delete-orphan"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        "Prediction", back_populates="asset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset {self.exchange}:{self.ticker}>"


# ---------------------------------------------------------------------------
# 2. social_posts — dedupe by (source, content_hash). No usernames stored.
# ---------------------------------------------------------------------------
class SocialPost(Base):
    __tablename__ = "social_posts"
    __table_args__ = (
        UniqueConstraint("source", "content_hash", name="uq_social_posts_source_hash"),
        Index("ix_social_posts_asset_published", "asset_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. x, facebook, linkedin
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # Engagement may be unknown — NULL, never 0.
    engagement: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )

    asset: Mapped[Asset] = relationship("Asset", back_populates="social_posts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SocialPost source={self.source} hash={self.content_hash[:8]}…>"


# ---------------------------------------------------------------------------
# 3. news_articles — dedupe by url_hash.
# ---------------------------------------------------------------------------
class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("url_hash", name="uq_news_articles_url_hash"),
        Index("ix_news_articles_asset_published", "asset_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hex of URL
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )

    asset: Mapped[Optional[Asset]] = relationship("Asset", back_populates="news_articles")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NewsArticle hash={self.url_hash[:8]}…>"


# ---------------------------------------------------------------------------
# 4. market_prices — one row per (asset, trade_date, provider). NUMERIC(18,4).
# ---------------------------------------------------------------------------
class MarketPrice(Base):
    __tablename__ = "market_prices"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "trade_date", "provider", name="uq_market_prices_asset_date_provider"
        ),
        Index("ix_market_prices_asset_date", "asset_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. twelve_data
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    high: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    low: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    close: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # NULL = unknown
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )

    asset: Mapped[Asset] = relationship("Asset", back_populates="market_prices")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MarketPrice asset={self.asset_id} {self.trade_date} {self.provider}>"


# ---------------------------------------------------------------------------
# 5. sentiment_results — one row per (item_type, item_id, model_name).
# ---------------------------------------------------------------------------
class SentimentResult(Base):
    __tablename__ = "sentiment_results"
    __table_args__ = (
        UniqueConstraint(
            "item_type", "item_id", "model_name", name="uq_sentiment_item_model"
        ),
        CheckConstraint(
            "item_type IN ('social_post', 'news_article')", name="ck_sentiment_item_type"
        ),
        CheckConstraint(
            "label IN ('positive', 'neutral', 'negative')", name="ck_sentiment_label"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_type: Mapped[str] = mapped_column(String(16), nullable=False)  # social_post / news_article
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(16), nullable=False)  # positive/neutral/negative
    score: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)  # P(pos)-P(neg)
    p_pos: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    p_neu: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    p_neg: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SentimentResult {self.item_type}#{self.item_id} {self.label}>"


# ---------------------------------------------------------------------------
# 6. predictions — one row per (asset, target_date, model_version).
# ---------------------------------------------------------------------------
class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "target_date", "model_version", name="uq_predictions_asset_date_version"
        ),
        Index("ix_predictions_target_date", "target_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    made_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )
    predicted_return: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    predicted_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    # Filled in later by the actual-close backfill job; NULL until then.
    actual_close: Mapped[Optional[float]] = mapped_column(Numeric(18, 4), nullable=True)
    # True while sentiment features overlap is insufficient (see master prompt).
    experimental: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )

    asset: Mapped[Asset] = relationship("Asset", back_populates="predictions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prediction asset={self.asset_id} {self.target_date} v={self.model_version}>"


# ---------------------------------------------------------------------------
# 7. model_evaluations — per-version metrics, including baselines and n_test.
# ---------------------------------------------------------------------------
class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    __table_args__ = (
        UniqueConstraint("model_version", name="uq_model_evaluations_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    mae: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    rmse: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    directional_accuracy: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    # Baseline numbers on the same test windows (no-change and always-up).
    baseline_nochange_mae: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    baseline_nochange_rmse: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)
    baseline_nochange_dir_acc: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    baseline_alwaysup_dir_acc: Mapped[Optional[float]] = mapped_column(Numeric(8, 6), nullable=True)
    n_test: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # real runs only
    params: Mapped[Optional[dict]] = mapped_column(JSONColumn(), nullable=True)
    git_commit: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    trained_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ModelEvaluation v={self.model_version} n_test={self.n_test}>"


# ---------------------------------------------------------------------------
# 8. collection_jobs — queue. Unique dedupe_key prevents double-scheduling.
# ---------------------------------------------------------------------------
class CollectionJob(Base):
    __tablename__ = "collection_jobs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_collection_jobs_dedupe_key"),
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_jobs_status"
        ),
        Index("ix_jobs_status_run_after", "status", "run_after"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)  # collect/score/train
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default=text("'queued'")
    )
    params: Mapped[Optional[dict]] = mapped_column(JSONColumn(), nullable=True)
    run_after: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counts: Mapped[Optional[dict]] = mapped_column(JSONColumn(), nullable=True)
    claimed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, server_default=_server_ts()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now, server_default=_server_ts()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CollectionJob {self.dedupe_key} {self.status}>"


__all__ = [
    "Asset",
    "SocialPost",
    "NewsArticle",
    "MarketPrice",
    "SentimentResult",
    "Prediction",
    "ModelEvaluation",
    "CollectionJob",
]
