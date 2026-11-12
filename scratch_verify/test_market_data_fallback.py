"""Test market-data fallback for all 10 HKEX/KRX assets."""
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, r"C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent\backend")
os.chdir(r"C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent")

from app.core.config import get_settings
from app.collectors.chain import market_provider_chain, fetch_daily_prices

settings = get_settings()
print(f"Primary provider: {settings.market_data_provider or 'twelvedata'}")
print(f"Fallback: {settings.market_data_fallback}")
print()

# Test all 10 assets
assets = [
    ("0700", "HKEX", "Tencent"),
    ("9988", "HKEX", "Alibaba"),
    ("1810", "HKEX", "Xiaomi"),
    ("3690", "HKEX", "Meituan"),
    ("0005", "HKEX", "HSBC"),
    ("005930", "KRX", "Samsung Electronics"),
    ("000660", "KRX", "SK Hynix"),
    ("035420", "KRX", "NAVER"),
    ("035720", "KRX", "Kakao"),
    ("005380", "KRX", "Hyundai Motor"),
]

end = date.today() - timedelta(days=1)  # yesterday
start = end - timedelta(days=5)  # 5-day window

results = []
for ticker, exchange, name in assets:
    print(f"Testing {exchange}:{ticker} ({name})...")
    try:
        chain = market_provider_chain(settings, ticker, start, end, exchange=exchange)
        provider, rows, attempts = fetch_daily_prices(chain)

        print(f"  ✓ Provider: {provider.provider_name}")
        print(f"    Rows: {len(rows)}")
        print(f"    Attempts: {attempts}")
        if rows:
            print(f"    Latest: {rows[-1].trade_date} close={rows[-1].close}")

        results.append({
            "ticker": ticker,
            "exchange": exchange,
            "name": name,
            "provider": provider.provider_name,
            "rows": len(rows),
            "success": len(rows) > 0,
            "attempts": attempts,
        })
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {str(e)[:200]}")
        results.append({
            "ticker": ticker,
            "exchange": exchange,
            "name": name,
            "provider": "FAILED",
            "rows": 0,
            "success": False,
            "error": str(e)[:200],
        })
    print()

print("\n" + "="*70)
print("SUMMARY")
print("="*70)
for r in results:
    status = "✓" if r["success"] else "✗"
    print(f"{status} {r['exchange']:4} {r['ticker']:6} {r['name']:20} → {r['provider']:12} ({r['rows']} rows)")

success_count = sum(1 for r in results if r["success"])
print(f"\nTotal: {success_count}/{len(results)} assets successfully fetched")

import json
print("\nDetailed attempts:")
for r in results:
    if "attempts" in r:
        print(f"{r['ticker']}: {json.dumps(r['attempts'], indent=2)}")
