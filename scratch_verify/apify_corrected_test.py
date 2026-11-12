"""Apify: verify auth + test Actor access with correct ~ separator."""
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
c = httpx.Client(timeout=90)

# 1. Auth check
r = c.get("https://api.apify.com/v2/users/me", headers=h)
print(f"[AUTH] GET /v2/users/me -> HTTP {r.status_code}")
if r.status_code != 200:
    print(f"  FAILED: {r.text[:300]}")
    raise SystemExit("auth failed")
print("  ✓ authenticated\n")

actors = [
    ("lofomachines~telegram-keyword-search-scraper", "telegram", {"keyword": "Tencent stock", "maxPosts": 5}),
    ("hgservices~naver-stock-discussion-scraper", "naver", {"stocks": ["005930"], "maxResults": 10}),
    ("ardent_fork~daum-news", "daum", {"sections": ["economy"], "maxItems": 10, "fetchArticles": True}),
    ("claude_code_reviewer~hkgolden-scraper", "hkgolden", {"keyword": "Tencent", "maxPosts": 10}),
]

for actor_ref, label, test_input in actors:
    print(f"===== {label.upper()}: {actor_ref} =====")

    # GET actor metadata
    r = c.get(f"https://api.apify.com/v2/acts/{actor_ref}", headers=h)
    print(f"GET /v2/acts/{actor_ref} -> HTTP {r.status_code}")

    if r.status_code == 404:
        print(f"  404 Not Found — trying to retrieve unique ID from Store search...")
        # Search store for this actor
        search_term = actor_ref.split("~")[1] if "~" in actor_ref else actor_ref
        rs = c.get("https://api.apify.com/v2/store", headers=h, params={"search": search_term, "limit": 20})
        if rs.status_code == 200:
            items = rs.json().get("data", {}).get("items", [])
            username_part = actor_ref.split("~")[0]
            name_part = actor_ref.split("~")[1] if "~" in actor_ref else ""
            match = None
            for item in items:
                if item.get("username") == username_part and item.get("name") == name_part:
                    match = item
                    break
            if match:
                unique_id = match.get("id")
                print(f"  Found in Store: id={unique_id}, trying that...")
                r = c.get(f"https://api.apify.com/v2/acts/{unique_id}", headers=h)
                print(f"  GET /v2/acts/{unique_id} -> HTTP {r.status_code}")
                if r.status_code != 200:
                    print(f"    Still failed: {r.text[:300]}")
                    print()
                    continue
                actor_ref = unique_id  # use this for the run
            else:
                print(f"  Not found in Store results")
                print()
                continue
        else:
            print(f"  Store search failed: HTTP {rs.status_code}")
            print()
            continue

    if r.status_code != 200:
        print(f"  Error: {r.text[:300]}")
        print()
        continue

    d = r.json().get("data", {})
    actor_id = d.get("id")
    print(f"  ✓ id={actor_id} public={d.get('isPublic')} deprecated={d.get('isDeprecated')}")
    print(f"    name={d.get('name')} title={d.get('title')[:60]}")

    ver = d.get("defaultRunOptions", {}).get("build") or d.get("versions", [{}])[0] if d.get("versions") else {}
    schema = ver.get("inputSchema") if isinstance(ver, dict) else None
    if schema:
        print(f"  inputSchema keys: {list(schema.get('properties', {}).keys())[:10]}")

    # Run the actor with bounded test input
    print(f"  Running actor (bounded test)...")
    run_payload = test_input.copy()
    r_run = c.post(
        f"https://api.apify.com/v2/acts/{actor_ref}/runs",
        headers=h,
        json=run_payload,
        params={"timeout": 120, "memory": 256}  # 2min timeout, 256MB
    )
    print(f"  POST /v2/acts/{actor_ref}/runs -> HTTP {r_run.status_code}")
    if r_run.status_code not in (200, 201):
        print(f"    Error: {r_run.text[:400]}")
        print()
        continue

    run_data = r_run.json().get("data", {})
    run_id = run_data.get("id")
    print(f"  ✓ Run started: id={run_id} status={run_data.get('status')}")

    # Poll for completion (max 2 min)
    for i in range(24):  # 24 * 5s = 120s
        time.sleep(5)
        r_status = c.get(f"https://api.apify.com/v2/acts/{actor_ref}/runs/{run_id}", headers=h)
        if r_status.status_code == 200:
            run_info = r_status.json().get("data", {})
            status = run_info.get("status")
            print(f"    [{i*5}s] status={status}")
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break
        else:
            print(f"    Poll failed: HTTP {r_status.status_code}")
            break

    # Get dataset
    if run_info.get("defaultDatasetId"):
        ds_id = run_info["defaultDatasetId"]
        r_ds = c.get(f"https://api.apify.com/v2/datasets/{ds_id}/items", headers=h, params={"limit": 10})
        print(f"  GET dataset {ds_id} -> HTTP {r_ds.status_code}")
        if r_ds.status_code == 200:
            items = r_ds.json()
            print(f"  ✓ Dataset: {len(items)} items")
            if items:
                print(f"    Sample keys: {list(items[0].keys())[:10]}")
        else:
            print(f"    Dataset error: {r_ds.text[:200]}")
    else:
        print(f"  No dataset ID in run result")

    print()

print("DONE")
