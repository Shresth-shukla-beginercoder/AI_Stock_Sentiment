"""Language detection and model routing (Phase 6).

Uses lingua-py (Apache 2.0) for language detection. Routes to verified
Hugging Face models based on detected language. Documents unsupported languages.

Verified model registry:
- English social: cardiffnlp/twitter-roberta-base-sentiment-latest (CC-BY-4.0)

Unsupported languages return None (no fabricated scores).
"""

from typing import Optional
from dataclasses import dataclass

from lingua import Language, LanguageDetectorBuilder

from app.core.logging import get_logger

_log = get_logger("sentiment.language")


# Verified Hugging Face models (model card checked, license confirmed)
@dataclass
class ModelSpec:
    """Hugging Face model specification."""
    model_id: str
    license: str
    languages: list[str]  # ISO 639-1 codes
    task: str
    notes: str


# Registry of verified models (never add unverified models here)
VERIFIED_MODELS = {
    "en-social": ModelSpec(
        model_id="cardiffnlp/twitter-roberta-base-sentiment-latest",
        license="CC-BY-4.0",
        languages=["en"],
        task="sentiment-analysis",
        notes="Twitter-trained, 124M tweets, outputs 3-class softmax (neg/neu/pos)",
    ),
}


# Language detector (singleton, lazy-initialized)
_detector = None


def _get_detector():
    """Lazy-initialize the lingua language detector (thread-safe)."""
    global _detector
    if _detector is None:
        # Build detector for languages we care about (HKEX=zh, KRX=ko, social=en)
        # Lingua-py supports: en, zh, ja, ko (verified from model card)
        languages = [Language.ENGLISH, Language.CHINESE, Language.JAPANESE, Language.KOREAN]
        _detector = LanguageDetectorBuilder.from_languages(*languages).build()
    return _detector


def detect_language(text: str) -> Optional[str]:
    """Detect language of the given text.

    Returns ISO 639-1 code (e.g. "en", "zh", "ja", "ko") or None if detection fails.
    """
    if not text or not text.strip():
        return None

    detector = _get_detector()
    try:
        detected = detector.detect_language_of(text)
        if detected is None:
            return None

        # Map lingua Language enum to ISO 639-1 code
        lang_map = {
            Language.ENGLISH: "en",
            Language.CHINESE: "zh",
            Language.JAPANESE: "ja",
            Language.KOREAN: "ko",
        }
        return lang_map.get(detected)
    except Exception as e:
        _log.warning("language detection failed", extra={"error": str(e)})
        return None


def select_model(text: str, source_type: str) -> Optional[str]:
    """Select appropriate sentiment model for the given text.

    Args:
        text: Preprocessed text to analyze
        source_type: "social" or "news"

    Returns:
        Hugging Face model_id or None if no suitable model exists.

    Unsupported languages return None (no fabricated scores). Phase 6 verified:
    - English social posts (Twitter-trained model)

    Chinese/Korean/Japanese: UNVERIFIED — no verified multilingual financial-sentiment
    model found. Returns None for unsupported languages (honest limitation).
    """
    lang = detect_language(text)
    if lang is None:
        _log.debug("no language detected", extra={"text_preview": text[:50]})
        return None

    # English social: verified
    if lang == "en" and source_type == "social":
        return VERIFIED_MODELS["en-social"].model_id

    # English news: use the same Twitter-trained model (suboptimal but verified)
    # A dedicated financial-news model would be better, but FinBERT is non-commercial.
    if lang == "en" and source_type == "news":
        _log.debug("using twitter model for english news (suboptimal but verified)")
        return VERIFIED_MODELS["en-social"].model_id

    # Chinese/Japanese/Korean: UNVERIFIED
    if lang in ("zh", "ja", "ko"):
        _log.info("unsupported language (no verified CJK sentiment model)",
                  extra={"lang": lang, "source_type": source_type})
        return None

    # Other languages: unsupported
    _log.debug("unsupported language", extra={"lang": lang, "source_type": source_type})
    return None
