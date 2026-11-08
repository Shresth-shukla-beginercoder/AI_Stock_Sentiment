"""Text preprocessing for sentiment analysis (Phase 6).

Reuses Phase 5 normalization utilities. Strips URLs, extra whitespace, and
rejects empty text. Preserves original text in the database.
"""

from typing import Optional
import re

from app.collectors.normalize import clean_text


_URL_PATTERN = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
)


def preprocess_for_sentiment(text: Optional[str]) -> Optional[str]:
    """Prepare text for sentiment analysis.

    Steps:
    1. Apply Phase 5 clean_text (NFKC, HTML decode, tag strip, whitespace collapse)
    2. Strip URLs (replace with empty string)
    3. Collapse multiple spaces to single space
    4. Strip leading/trailing whitespace
    5. Reject if empty after cleaning

    Returns cleaned text or None if empty/invalid.
    """
    if not text:
        return None

    # Phase 5 normalization (NFKC, HTML decode, tag strip, whitespace)
    cleaned = clean_text(text)
    if not cleaned:
        return None

    # Strip URLs
    cleaned = _URL_PATTERN.sub("", cleaned)

    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Strip leading/trailing whitespace
    cleaned = cleaned.strip()

    # Reject empty
    if not cleaned:
        return None

    return cleaned
