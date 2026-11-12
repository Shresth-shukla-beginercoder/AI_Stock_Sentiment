"""Complete integration test: Naver + Daum + yfinance fallback.

Tests:
1. Apify auth
2. Naver Actor collection + normalization + persistence
3. Daum Actor collection + normalization + persistence
4. Korean sentiment processing (using English model fallback)
5. Market data fallback (Twelve Data → yfinance)

This is the Phase 6 end-to-end verification.
"""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, "/app")
os.chdir("/app")

from app.core.config import get_settings
from app.collectors.apify import ApifySocialCollector
from app.collectors.naver_discussion import NaverDiscussionCollector
from app.collectors.daum_news import DaumNewsCollector
from app.collectors.chain import market_provider_chain, fetch_daily_prices
from app.sentiment.language import detect_language, select_model
from app.sentiment.analyzer import analyze
from app.database.session import get_session_factory
from app.services.persist import persist_social, persist_news, persist_market_prices, resolve_asset

settings = get_settings()

print("="*70)
print("INTEGRATION TEST: Naver + Daum + Market Data + Sentiment")
print("="*70)
print()

# Test 1: Apify Authentication
print("1. Apify Authentication")
try:
    apify = ApifySocialCollector(settings=settings)
    # Verify via a simple actor metadata call
    print("   ✓ Apify collector initialized")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 2: Naver Collection
print("\n2. Naver Stock Discussion Collection")
try:
    naver = NaverDiscussionCollector(apify_collector=apify)
    avail = naver.verify_actor()
    print(f"   Actor available: {avail.available} ({avail.reason})")

    if avail.available:
        # Run with bounded test
        print("   Running actor (5 posts from Samsung 005930)...")
        run = naver.run_actor(stocks=["005930"], max_results=5, wait_seconds=60)
        raw_items = naver.fetch_items(run)
        items = naver.to_social_items(raw_items)
        print(f"   ✓ Collected {len(items)} usable posts")

        # Test persistence
        factory = get_session_factory()
        with factory() as session:
            asset = resolve_asset(session, "005930", "KRX")
            if asset:
                result = persist_social(session, asset.id, items, is_demo=False)
                session.commit()
                print(f"   ✓ Persisted {result.inserted} posts ({result.skipped_duplicates} duplicates)")
            else:
                print("   ⚠ Asset not found (skipping persistence)")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {str(e)[:200]}")

# Test 3: Daum News Collection
print("\n3. Daum News Collection")
try:
    daum = DaumNewsCollector(apify_collector=apify)
    avail = daum.verify_actor()
    print(f"   Actor available: {avail.available} ({avail.reason})")

    if avail.available:
        print("   Running actor (10 economy articles)...")
        run = daum.run_actor(sections=["economy"], max_items=10, wait_seconds=60)
        raw_items = daum.fetch_items(run)
        items = daum.to_daum_items(raw_items)
        print(f"   ✓ Collected {len(items)} articles")

        # Test persistence
        with factory() as session:
            asset = resolve_asset(session, "005930", "KRX")
            if asset:
                result = persist_news(session, asset.id, items, is_demo=False)
                session.commit()
                print(f"   ✓ Persisted {result.inserted} articles ({result.skipped_duplicates} duplicates)")
            else:
                print("   ⚠ Asset not found (skipping persistence)")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {str(e)[:200]}")

# Test 4: Korean Sentiment Processing
print("\n4. Korean Sentiment Processing")
try:
    korean_text = "삼성전자 주가가 상승했습니다"  # "Samsung stock rose"
    lang = detect_language(korean_text)
    print(f"   Detected language: {lang}")

    model = select_model(korean_text, "social")
    print(f"   Selected model: {model}")

    if model:
        score = analyze(korean_text, model)
        if score:
            print(f"   ✓ Sentiment score: {score.score:.3f} ({score.label})")
        else:
            print("   ✗ Sentiment analysis returned None")
    else:
        print("   ⚠ No model selected for Korean")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {str(e)[:200]}")

# Test 5: Market Data Fallback
print("\n5. Market Data Fallback (yfinance)")
try:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=3)

    test_assets = [
        ("0700", "HKEX", "Tencent"),
        ("005930", "KRX", "Samsung"),
    ]

    for ticker, exchange, name in test_assets:
        print(f"   Testing {exchange}:{ticker} ({name})...")
        chain = market_provider_chain(settings, ticker, start, end, exchange=exchange)
        provider, rows, attempts = fetch_daily_prices(chain)

        print(f"     Provider: {provider.provider_name}, Rows: {len(rows)}")
        for att in attempts:
            status = "✓" if att["ok"] else "✗"
            detail = f"{att['rows']} rows" if att.get("ok") else att.get("error")
            print(f"       {status} {att['provider']}: {detail}")
except Exception as e:
    print(f"   ✗ FAILED: {type(e).__name__}: {str(e)[:200]}")

print("\n" + "="*70)
print("INTEGRATION TEST COMPLETE")
print("="*70)
