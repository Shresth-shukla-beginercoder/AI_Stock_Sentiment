"""Sentiment analysis pipeline (Phase 6).

Full pipeline: cleaner → language detection → model selection → inference → persistence

Components:
- cleaner: Text preprocessing (reuses Phase 5 normalize.clean_text, strips URLs)
- language: Lingua-py detector (Apache 2.0, supports en/zh/ja/ko)
- analyzer: Hugging Face transformers, CPU inference, lazy model loading
- aggregate: Engagement weighting, social/news combination, per-asset aggregation
- persist: Concurrent-safe sentiment_results upsert

Verified models:
- English social: cardiffnlp/twitter-roberta-base-sentiment-latest (CC-BY-4.0)

Unsupported languages (Chinese/Korean/Japanese): No verified CJK sentiment model found.
Returns None for unsupported languages (honest limitation).
"""

from app.sentiment.cleaner import preprocess_for_sentiment
from app.sentiment.language import detect_language, select_model, VERIFIED_MODELS
from app.sentiment.analyzer import analyze, SentimentScore
from app.sentiment.aggregate import aggregate_sentiment_for_asset, AggregatedSentiment
from app.sentiment.persist import persist_sentiment_result, PersistResult

__all__ = [
    "preprocess_for_sentiment",
    "detect_language",
    "select_model",
    "analyze",
    "aggregate_sentiment_for_asset",
    "persist_sentiment_result",
    "SentimentScore",
    "AggregatedSentiment",
    "PersistResult",
    "VERIFIED_MODELS",
]
