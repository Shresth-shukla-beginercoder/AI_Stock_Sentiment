"""Deep dive: HKGolden failure + Telegram empty result + full schema capture."""
import json
import os
import time
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
c = httpx.Client(timeout=120)

# 1. HKGolden - get run details and README
print("=== HKGolden Investigation ===")
actor = "claude_code_reviewer~hkgolden-scraper"
r = c.get(f"https://api.apify.com/v2/acts/{actor}", headers=h)
d = r.json().get("data", {})
print(f"Actor: {d.get('id')} public={d.get('isPublic')}")

# Get README
r_readme = c.get(f"https://api.apify.com/v2/acts/{actor}/readme", headers=h)
if r_readme.status_code == 200:
    readme_body = r_readme.json().get("body", "")[:3000]
    print(f"README ({len(readme_body)} chars):\n{readme_body[:2000]}\n")

# Get input schema from versions
vers = d.get("versions", [])
if vers:
    schema = vers[0].get("inputSchema", {})
    print(f"Input schema properties: {list(schema.get('properties', {}).keys())}")
    print(f"Required: {schema.get('required', [])}")
    print(f"Schema sample: {json.dumps(schema.get('properties', {}), indent=2, ensure_ascii=False)[:1500]}\n")

# Check recent failed run
r_runs = c.get(f"https://api.apify.com/v2/acts/{actor}/runs", headers=h, params={"limit": 3})
if r_runs.status_code == 200:
    runs = r_runs.json().get("data", {}).get("items", [])
    for run in runs[:2]:
        rid = run.get("id")
        status = run.get("status")
        print(f"Run {rid}: status={status}")
        # Get run details
        r_detail = c.get(f"https://api.apify.com/v2/acts/{actor}/runs/{rid}", headers=h)
        if r_detail.status_code == 200:
            detail = r_detail.json().get("data", {})
            print(f"  exitCode={detail.get('exitCode')} duration={detail.get('duration')}s")
            stats = detail.get("stats", {})
            print(f"  stats: {json.dumps(stats, indent=2)[:500]}")

# 2. Telegram - try different keywords
print("\n=== Telegram - Testing Different Keywords ===")
actor = "lofomachines~telegram-keyword-search-scraper"
keywords = ["Tencent", "0700", "Samsung", "stock market", "HKEX"]
for kw in keywords[:3]:
    print(f"\nTesting keyword: '{kw}'")
    r = c.post(
        f"https://api.apify.com/v2/acts/{actor}/runs",
        headers=h,
        json={"keyword": kw, "maxPosts": 5},
        params={"timeout": 60}
    )
    if r.status_code in (200, 201):
        run_id = r.json().get("data", {}).get("id")
        print(f"  Run started: {run_id}")
        # Wait briefly
        for _ in range(12):
            time.sleep(5)
            rs = c.get(f"https://api.apify.com/v2/acts/{actor}/runs/{run_id}", headers=h)
            status = rs.json().get("data", {}).get("status")
            if status in ("SUCCEEDED", "FAILED", "ABORTED"):
                print(f"  Status: {status}")
                break
        # Get dataset
        ds_id = rs.json().get("data", {}).get("defaultDatasetId")
        if ds_id:
            rds = c.get(f"https://api.apify.com/v2/datasets/{ds_id}/items", headers=h, params={"limit": 10})
            items = rds.json() if rds.status_code == 200 else []
            print(f"  Items: {len(items)}")
            if items:
                print(f"  Sample: {json.dumps(items[0], indent=2, ensure_ascii=False)[:500]}")
    else:
        print(f"  Failed: HTTP {r.status_code}")

# 3. Capture full schemas for all 4 actors
print("\n\n=== Full Input Schemas ===")
for actor_ref in [
    "lofomachines~telegram-keyword-search-scraper",
    "hgservices~naver-stock-discussion-scraper",
    "ardent_fork~daum-news",
    "claude_code_reviewer~hkgolden-scraper",
]:
    print(f"\n--- {actor_ref} ---")
    r = c.get(f"https://api.apify.com/v2/acts/{actor_ref}", headers=h)
    if r.status_code == 200:
        d = r.json().get("data", {})
        vers = d.get("versions", [])
        if vers:
            schema = vers[0].get("inputSchema", {})
            props = schema.get("properties", {})
            print(f"Properties ({len(props)}):")
            for pname, pdef in list(props.items())[:15]:
                ptype = pdef.get("type", "any")
                pdesc = (pdef.get("description") or "")[:80]
                required = pname in schema.get("required", [])
                print(f"  {pname}: {ptype}" + (" (required)" if required else "") + f" - {pdesc}")
    else:
        print(f"  HTTP {r.status_code}")

print("\nDONE")
