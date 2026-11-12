"""Live credential / integration verification (read-only + bounded probes).

Loads .env from the repo root, NEVER prints key values, and runs one bounded
probe per provider so we can classify: valid auth / rate limit / plan gate /
invalid key / outage.
"""
import json
import os
import sys

REPO = r"C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent"
os.chdir(REPO)


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


env = load_env(os.path.join(REPO, ".env"))
have = {k: bool(env.get(k)) for k in [
    "EXA_API_KEY", "TAVILY_API_KEY", "APIFY_API_TOKEN",
    "APIFY_API_KEY", "TWELVE_DATA_API_KEY", "API_ADMIN_KEY",
    "MARKET_DATA_PROVIDER", "DATA_MODE",
]}
print("## .env presence (names only)")
for k in have:
    print(f"  {k}: {'set' if have[k] else 'MISSING'}")
print(f"  MARKET_DATA_PROVIDER={env.get('MARKET_DATA_PROVIDER','')!r}")
print(f"  DATA_MODE={env.get('DATA_MODE','')!r}")
print()


def mask(s):
    s = s or ""
    return (s[:6] + "..." + s[-4:]) if len(s) > 12 else "***"


# ---- Exa ----
print("## Exa")
try:
    import exa_py
    exa = exa_py.Exa(api_key=env.get("EXA_API_KEY"), timeout=30)
    resp = exa.search(query="Tencent Holdings stock news", num_results=3,
                      category="news")
    results = getattr(resp, "results", []) or []
    print(f"  search OK, {len(results)} results")
    for r in results[:3]:
        print(f"    - {getattr(r,'title','')[:70]!r} | {getattr(r,'url','')[:60]}")
except Exception as e:
    print(f"  Exa FAILED: {type(e).__name__}: {str(e)[:200]}")
print()

# ---- Tavily ----
print("## Tavily (key-only probe; no collector in code)")
try:
    import httpx
    r = httpx.post("https://api.tavily.com/search",
                   json={"api_key": env.get("TAVILY_API_KEY"),
                         "query": "Tencent Holdings news", "max_results": 2},
                   timeout=30)
    print(f"  HTTP {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        print(f"  key VALID; {len(d.get('results', []))} results")
    else:
        print(f"  body: {r.text[:200]}")
except Exception as e:
    print(f"  Tavily probe FAILED: {type(e).__name__}: {str(e)[:200]}")
print()

# ---- Apify ----
print("## Apify")
apify_key = env.get("APIFY_API_TOKEN") or env.get("APIFY_API_KEY")
print(f"  using token={mask(apify_key)}")
try:
    import httpx
    r = httpx.get("https://api.apify.com/v2/users/me",
                  headers={"Authorization": f"Bearer {apify_key}"}, timeout=30)
    print(f"  GET /v2/users/me -> HTTP {r.status_code}")
    if r.status_code == 200:
        print(f"  authenticated user: {r.json().get('username')}")
    else:
        print(f"  body: {r.text[:300] or '(empty)'}")
except Exception as e:
    print(f"  Apify probe FAILED: {type(e).__name__}: {str(e)[:200]}")
print()

# ---- Twelve Data ----
print("## Twelve Data")
td = env.get("TWELVE_DATA_API_KEY")
print(f"  using key={mask(td)}")
import httpx
for sym in ("0700.HK", "005930.KS", "AAPL"):
    try:
        r = httpx.get("https://api.twelvedata.com/quote",
                      params={"symbol": sym, "apikey": td}, timeout=30)
        body = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
        status = body.get("status", r.status_code)
        msg = body.get("message", body.get("code", ""))
        print(f"  {sym}: HTTP {r.status_code} status={status!r} {str(msg)[:80]}")
    except Exception as e:
        print(f"  {sym} FAILED: {type(e).__name__}: {str(e)[:120]}")
print()

# ---- Admin API key vs running backend ----
print("## Admin API key (local backend :8000)")
adm = env.get("API_ADMIN_KEY")
print(f"  using admin key={mask(adm)}")
try:
    r = httpx.get("http://localhost:8000/api/jobs", params={"limit": 1}, timeout=10)
    print(f"  no-key /api/jobs -> HTTP {r.status_code}")
    r = httpx.get("http://localhost:8000/api/jobs", params={"limit": 1},
                  headers={"X-API-Key": adm}, timeout=10)
    print(f"  with-key /api/jobs -> HTTP {r.status_code}")
except Exception as e:
    print(f"  backend probe FAILED (is backend up?): {type(e).__name__}: {str(e)[:150]}")
print()
print("DONE")
