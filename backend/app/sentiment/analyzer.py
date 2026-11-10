"""Sentiment analysis via Hugging Face transformers (Phase 6).

Lazy model loading, CPU inference, deterministic score calculation.
Outputs positive/negative probabilities and a single sentiment score.

Score = P(positive) - P(negative), range [-1, 1]
Label thresholds (CLAUDE.md):
- Bullish: score > 0.15
- Bearish: score < -0.15
- Neutral: otherwise
"""

from typing import Optional
from dataclasses import dataclass
import os

from transformers import pipeline

from app.core.config import get_settings
from app.core.logging import get_logger

_log = get_logger("sentiment.analyzer")


@dataclass
class SentimentScore:
    """Sentiment analysis result."""
    model_id: str
    label: str  # positive, neutral, negative
    score: float  # P(pos) - P(neg), range [-1, 1]
    p_pos: float  # P(positive)
    p_neu: float  # P(neutral)
    p_neg: float  # P(negative)


# Lazy-loaded pipelines (one per model)
_pipelines: dict[str, object] = {}

# The verified RoBERTa sentiment model has a 514-token context window. The
# ``pipeline`` call does NOT truncate by default, so a long news/social body
# tokenizes to more than 514 tokens and RoBERTa's embedding gather
# (``torch.gather(token_type_ids, index=position_ids)`` on a 514-slot buffer)
# raises ``index out of bounds``. Truncating to a safe content-token limit
# before inference keeps long documents working while leaving short text — the
# overwhelming case — byte-for-byte unchanged.
_MAX_INFER_TOKENS = 512


def _get_pipeline(model_id: str):
    """Lazy-load sentiment pipeline for the given model.

    Caches the pipeline in memory and on disk (HF_HOME env var or hf_cache_dir).
    Thread-safe: transformers pipelines handle concurrent inference.
    """
    if model_id in _pipelines:
        return _pipelines[model_id]

    # Set Hugging Face cache directory (mounted volume for persistence)
    settings = get_settings()
    os.environ["HF_HOME"] = settings.hf_cache_dir

    try:
        _log.info("loading sentiment model", extra={"model_id": model_id})
        pipe = pipeline("sentiment-analysis", model=model_id, device=-1)  # device=-1: CPU
        _pipelines[model_id] = pipe
        _log.info("model loaded", extra={"model_id": model_id})
        return pipe
    except Exception as e:
        _log.error("failed to load model", extra={"model_id": model_id, "error": str(e)})
        raise


def analyze(text: str, model_id: str) -> Optional[SentimentScore]:
    """Perform sentiment analysis on the given text.

    Args:
        text: Preprocessed text (non-empty, no URLs)
        model_id: Verified Hugging Face model ID

    Returns:
        SentimentScore with probabilities and derived score, or None on failure.

    Never returns a fabricated score. Failures are logged and None is returned.
    """
    if not text or not text.strip():
        return None

    try:
        pipe = _get_pipeline(model_id)
        result = pipe(
            text,
            truncation=True,
            max_length=_MAX_INFER_TOKENS,
            return_all_scores=True,
            top_k=None,
        )

        # transformers returns the label/score sequence differently by version
        # and input type: a list-input gives [[{label,score}, ...], ...] while a
        # single-string input (newer transformers, e.g. 5.x) gives a flat
        # [{label,score}, ...]. Normalize to the inner sequence of dicts so the
        # parser works for both.
        if not result:
            _log.warning("empty inference result", extra={"model_id": model_id})
            return None
        first = result[0]
        items = first if isinstance(first, list) else result
        if not items:
            _log.warning("empty inference result", extra={"model_id": model_id})
            return None

        scores_dict = {str(item["label"]).lower(): float(item["score"]) for item in items}

        # Extract probabilities (model-specific labels normalized)
        p_pos = scores_dict.get("positive", 0.0)
        p_neu = scores_dict.get("neutral", 0.0)
        p_neg = scores_dict.get("negative", 0.0)

        # Fallback: some models use "negative", "neutral", "positive"
        # Ensure they sum to approximately 1.0
        if p_pos + p_neu + p_neg < 0.01:
            _log.warning("invalid score distribution", extra={"scores": scores_dict})
            return None

        # Normalize to ensure they sum to 1.0 (in case of rounding errors)
        total = p_pos + p_neu + p_neg
        p_pos /= total
        p_neu /= total
        p_neg /= total

        # Calculate sentiment score
        sentiment_score = p_pos - p_neg  # range [-1, 1]

        # Determine label based on thresholds (CLAUDE.md)
        settings = get_settings()
        if sentiment_score > settings.sentiment_threshold_bullish:
            label = "positive"
        elif sentiment_score < settings.sentiment_threshold_bearish:
            label = "negative"
        else:
            label = "neutral"

        return SentimentScore(
            model_id=model_id,
            label=label,
            score=round(sentiment_score, 6),
            p_pos=round(p_pos, 6),
            p_neu=round(p_neu, 6),
            p_neg=round(p_neg, 6),
        )
    except Exception as e:
        _log.error("sentiment analysis failed", extra={
            "model_id": model_id,
            "text_preview": text[:50],
            "error": str(e),
        })
        return None
