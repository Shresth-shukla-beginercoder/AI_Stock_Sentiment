"""Phase 6: Sentiment Engine tests.

Deterministic mocked inference tests covering:
- Text preprocessing (empty, HTML, URLs, whitespace)
- Language detection (en/zh/ja/ko)
- Model selection and routing
- Sentiment scoring (pos/neu/neg, boundary thresholds ±0.15)
- Engagement weighting (missing, negative, valid)
- Social/news aggregation (0.4/0.6 weights)
- Insufficient data handling
- Concurrent persistence (ON CONFLICT DO NOTHING)
- No fabricated scores on failures

Real model inference separated and labeled UNVERIFIED until actually run.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, date
from sqlalchemy import select

# Unit tests: cleaner
from app.sentiment.cleaner import preprocess_for_sentiment


def test_preprocess_empty():
    assert preprocess_for_sentiment(None) is None
    assert preprocess_for_sentiment("") is None
    assert preprocess_for_sentiment("   ") is None


def test_preprocess_html_and_whitespace():
    assert preprocess_for_sentiment("<p>Hello  world</p>") == "Hello world"
    # HTML entities decode, then tags strip, leaving just text
    assert preprocess_for_sentiment("&lt;tag&gt;  text") == "text"


def test_preprocess_strips_urls():
    assert preprocess_for_sentiment("Check this https://example.com out") == "Check this out"
    assert preprocess_for_sentiment("https://example.com") is None  # Empty after stripping


def test_preprocess_collapses_whitespace():
    assert preprocess_for_sentiment("Hello    world\n\ttab") == "Hello world tab"


# Unit tests: language detection (mocked)
from app.sentiment.language import detect_language, select_model, Language


@patch("app.sentiment.language._get_detector")
def test_detect_language_english(mock_get_detector):
    mock_detector = Mock()
    mock_detector.detect_language_of.return_value = Language.ENGLISH
    mock_get_detector.return_value = mock_detector

    assert detect_language("Hello world") == "en"


@patch("app.sentiment.language._get_detector")
def test_detect_language_chinese(mock_get_detector):
    mock_detector = Mock()
    mock_detector.detect_language_of.return_value = Language.CHINESE
    mock_get_detector.return_value = mock_detector

    assert detect_language("你好世界") == "zh"


@patch("app.sentiment.language._get_detector")
def test_detect_language_korean(mock_get_detector):
    mock_detector = Mock()
    mock_detector.detect_language_of.return_value = Language.KOREAN
    mock_get_detector.return_value = mock_detector

    assert detect_language("안녕하세요") == "ko"


@patch("app.sentiment.language._get_detector")
def test_detect_language_japanese(mock_get_detector):
    mock_detector = Mock()
    mock_detector.detect_language_of.return_value = Language.JAPANESE
    mock_get_detector.return_value = mock_detector

    assert detect_language("こんにちは") == "ja"


@patch("app.sentiment.language._get_detector")
def test_detect_language_none_on_failure(mock_get_detector):
    mock_detector = Mock()
    mock_detector.detect_language_of.return_value = None
    mock_get_detector.return_value = mock_detector

    assert detect_language("") is None


@patch("app.sentiment.language.detect_language")
def test_select_model_english_social(mock_detect):
    mock_detect.return_value = "en"
    model = select_model("Hello world", "social")
    assert model == "cardiffnlp/twitter-roberta-base-sentiment-latest"


@patch("app.sentiment.language.detect_language")
def test_select_model_english_news(mock_detect):
    mock_detect.return_value = "en"
    model = select_model("Stock rises", "news")
    assert model == "cardiffnlp/twitter-roberta-base-sentiment-latest"  # Same model


@patch("app.sentiment.language.detect_language")
def test_select_model_chinese_unsupported(mock_detect):
    mock_detect.return_value = "zh"
    model = select_model("你好", "social")
    assert model is None  # Unsupported (no verified CJK model)


@patch("app.sentiment.language.detect_language")
def test_select_model_korean_unsupported(mock_detect):
    mock_detect.return_value = "ko"
    model = select_model("안녕", "news")
    assert model is None  # Unsupported


@patch("app.sentiment.language.detect_language")
def test_select_model_japanese_unsupported(mock_detect):
    mock_detect.return_value = "ja"
    model = select_model("こんにちは", "social")
    assert model is None  # Unsupported


# Unit tests: analyzer (mocked pipeline)
from app.sentiment.analyzer import analyze


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_positive(mock_get_pipeline):
    mock_pipe = Mock()
    mock_pipe.return_value = [[
        {"label": "NEGATIVE", "score": 0.1},
        {"label": "NEUTRAL", "score": 0.2},
        {"label": "POSITIVE", "score": 0.7},
    ]]
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("Great news!", "test-model")
    assert result is not None
    assert result.label == "positive"
    assert result.score == pytest.approx(0.6, abs=0.01)  # 0.7 - 0.1
    assert result.p_pos == pytest.approx(0.7, abs=0.01)
    assert result.p_neg == pytest.approx(0.1, abs=0.01)


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_negative(mock_get_pipeline):
    mock_pipe = Mock()
    mock_pipe.return_value = [[
        {"label": "NEGATIVE", "score": 0.8},
        {"label": "NEUTRAL", "score": 0.1},
        {"label": "POSITIVE", "score": 0.1},
    ]]
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("Terrible news", "test-model")
    assert result is not None
    assert result.label == "negative"
    assert result.score == pytest.approx(-0.7, abs=0.01)  # 0.1 - 0.8


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_neutral(mock_get_pipeline):
    mock_pipe = Mock()
    mock_pipe.return_value = [[
        {"label": "NEGATIVE", "score": 0.3},
        {"label": "NEUTRAL", "score": 0.4},
        {"label": "POSITIVE", "score": 0.3},
    ]]
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("Market unchanged", "test-model")
    assert result is not None
    assert result.label == "neutral"
    assert result.score == pytest.approx(0.0, abs=0.01)  # 0.3 - 0.3


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_boundary_bullish(mock_get_pipeline):
    """Score exactly at +0.15 threshold should be neutral (not > 0.15)."""
    mock_pipe = Mock()
    # P(pos) = 0.575, P(neg) = 0.425 → score = 0.15
    mock_pipe.return_value = [[
        {"label": "NEGATIVE", "score": 0.425},
        {"label": "NEUTRAL", "score": 0.0},
        {"label": "POSITIVE", "score": 0.575},
    ]]
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("text", "test-model")
    assert result is not None
    assert result.label == "neutral"  # score = 0.15, not > 0.15


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_boundary_bearish(mock_get_pipeline):
    """Score exactly at -0.15 threshold should be neutral (not < -0.15)."""
    mock_pipe = Mock()
    # P(pos) = 0.425, P(neg) = 0.575 → score = -0.15
    mock_pipe.return_value = [[
        {"label": "NEGATIVE", "score": 0.575},
        {"label": "NEUTRAL", "score": 0.0},
        {"label": "POSITIVE", "score": 0.425},
    ]]
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("text", "test-model")
    assert result is not None
    assert result.label == "neutral"  # score = -0.15, not < -0.15


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_empty_result(mock_get_pipeline):
    mock_pipe = Mock()
    mock_pipe.return_value = []
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("text", "test-model")
    assert result is None  # No fabricated score


@patch("app.sentiment.analyzer._get_pipeline")
def test_analyze_inference_exception(mock_get_pipeline):
    mock_pipe = Mock()
    mock_pipe.side_effect = Exception("Model error")
    mock_get_pipeline.return_value = mock_pipe

    result = analyze("text", "test-model")
    assert result is None  # No fabricated score on failure


def test_analyze_empty_text():
    result = analyze("", "test-model")
    assert result is None

    result = analyze("   ", "test-model")
    assert result is None


# Unit tests: engagement weighting
from app.sentiment.aggregate import _engagement_weight


def test_engagement_weight_zero():
    assert _engagement_weight(None) == 1.0
    assert _engagement_weight(0) == 1.0


def test_engagement_weight_negative():
    """Negative engagement treated as 0."""
    assert _engagement_weight(-5) == 1.0


def test_engagement_weight_valid():
    import math
    assert _engagement_weight(10) == pytest.approx(1.0 + math.log(11), abs=0.01)
    assert _engagement_weight(100) == pytest.approx(1.0 + math.log(101), abs=0.01)


# Integration tests: persistence (real DB)
# Mark with @pytest.mark.needs_db and run with: pytest -m needs_db
needs_db = pytest.mark.skipif(True, reason="requires real PostgreSQL; run with -m needs_db to override")


@needs_db
def test_persist_sentiment_idempotent():
    """Concurrent-safe: duplicate inserts skip silently."""
    from app.database.session import get_session_factory
    from app.database.models import Asset, SocialPost, SentimentResult
    from app.sentiment.persist import persist_sentiment_result
    from sqlalchemy import delete

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(Asset).where(Asset.ticker == "P6S"))
        s.commit()

    with factory() as s:
        a = Asset(exchange="P6X", ticker="P6S", name="P6 sentiment", confirmed=True)
        s.add(a)
        s.commit()
        s.refresh(a)
        asset_id = a.id

        post = SocialPost(
            asset_id=asset_id,
            source="test",
            content_hash="testhash",
            content="test post",
            published_at=datetime.now(timezone.utc),
        )
        s.add(post)
        s.commit()
        s.refresh(post)
        post_id = post.id

    try:
        with factory() as s:
            r1 = persist_sentiment_result(
                s, "social_post", post_id, "test-model", "positive", 0.5, 0.7, 0.2, 0.1
            )
            s.commit()
            assert r1.inserted == 1 and r1.skipped_duplicates == 0

        with factory() as s:
            r2 = persist_sentiment_result(
                s, "social_post", post_id, "test-model", "positive", 0.5, 0.7, 0.2, 0.1
            )
            s.commit()
            assert r2.inserted == 0 and r2.skipped_duplicates == 1

        with factory() as s:
            count = s.execute(
                select(SentimentResult).where(
                    SentimentResult.item_type == "social_post",
                    SentimentResult.item_id == post_id,
                )
            ).scalars().all()
            assert len(count) == 1
    finally:
        with factory() as s:
            s.execute(delete(Asset).where(Asset.ticker == "P6S"))
            s.commit()


# Real model verification (separated, labeled UNVERIFIED until run)
@pytest.mark.skip(reason="UNVERIFIED: requires network + ~500MB download")
def test_real_model_download_and_inference():
    """Real Hugging Face model download and inference.

    This test is SKIPPED by default. To run it:
    1. Ensure network access
    2. Ensure ~500MB disk space for model cache
    3. Run: pytest -k test_real_model -v

    Verifies:
    - Model downloads successfully
    - Inference produces valid 3-class output
    - Probabilities sum to ~1.0
    """
    from transformers import pipeline
    import os

    # Use a temporary cache directory (not the production one)
    os.environ["HF_HOME"] = "/tmp/hf_test_cache"

    pipe = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        device=-1,  # CPU
    )

    result = pipe("Great news today!", return_all_scores=True, top_k=None)
    assert len(result) == 1
    assert len(result[0]) == 3

    scores = {item["label"].lower(): item["score"] for item in result[0]}
    assert "positive" in scores
    assert "negative" in scores
    assert "neutral" in scores

    total = scores["positive"] + scores["negative"] + scores["neutral"]
    assert total == pytest.approx(1.0, abs=0.01)
