"""Apify: authenticate + fetch actor metadata/input schemas (read-only)."""
import json
import os
import httpx

REPO = r"C:\Users\shres\OneDrive\Desktop\AI - Stock_Sentiment -Agent"
os.chdir(REPO)


def load_env():
    env = {}
    with open(os.path.join(REPO, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


env = load_env()
tok = env.get("APIFY_API_TOKEN", "")
h = {"Authorization": f"Bearer {tok}"}
c = httpx.Client(timeout=60)

r = c.get("https://api.apify.com/v2/users/me", headers=h)
print(f"users/me -> HTTP {r.status_code}")
if r.status_code == 200:
    u = r.json()
    print(f"  authenticated: username={u.get('username')} username? plan={u.get('plan')}")
else:
    print(f"  body: {r.text[:300]}")
    raise SystemExit("auth failed - stopping")

for actor in [
    "lofomachines/telegram-keyword-search-scraper",
    "hgservices/naver-stock-discussion-scraper",
    "ardent_fork/daum-news",
    "claude_code_reviewer/hkgolden-scraper",
    "claude_code_reviewer/lihkg-scraper-en",
]:
    print(f"\n===== {actor} =====")
    r = c.get(f"https://api.apify.com/v2/acts/{actor}", headers=h)
    if r.status_code != 200:
        print(f"  GET actor -> HTTP {r.status_code}: {r.text[:200]}")
        continue
    d = r.json().get("data", {})
    ver = d.get("defaultVersion") or {}
    print(f"  id={d.get('id')} public={d.get('is_public')} deprecated={d.get('is_deprecated')}")
    print(f"  name={d.get('name')} title={d.get('title')}")
    print(f"  default_version={ver.get('versionNumber')} runCount={d.get('runCount')}")
    schema = ver.get("inputSchema")
    if schema:
        print("  inputSchema:")
        print("   " + json.dumps(schema, indent=1)[:2000])
    elif ver.get("inputSchemaHref"):
        r2 = c.get(f"https://api.apify.com/v2/acts/{actor}/versions/{ver.get('versionNumber')}/input-schema", headers=h)
        print("  inputSchemaHref ->", r2.status_code, json.dumps(r2.json() if r2.status_code == 200 else {}, indent=1)[:2000])
    # actor readme (for output field docs)
    r3 = c.get(f"https://api.apify.com/v2/acts/{actor}/readme", headers=h)
    if r3.status_code == 200:
        body = r3.json().get("body") or ""
        print(f"  README ({len(body)} chars): {body[:1500]}")
    print()
print("DONE")
