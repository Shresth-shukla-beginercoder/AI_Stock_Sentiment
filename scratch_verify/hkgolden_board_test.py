"""HKGolden: confirm canonical-ID run call works with board input."""
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
c = httpx.Client(timeout=180)

# 1. Confirm the unique ID is what GET returns
r = c.get("https://api.apify.com/v2/acts/claude_code_reviewer~hkgolden-scraper", headers=h)
d = r.json().get("data", {})
aid = d.get("id")
print(f"GET username~name form -> 200, canonical id={aid}")

# 2. Run the ACTOR ID directly (canonical form)
for inp in ({"board": ["finance"]}, {"boards": ["finance"]}, {"board": "finance"}):
    print(f"\n--- run POST /v2/acts/{aid}/runs with {json.dumps(inp)} ---")
    r = c.post(f"https://api.apify.com/v2/acts/{aid}/runs", headers=h,
               json=inp, params={"timeout": 90, "memory": 512})
    print(f"  HTTP {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"  body: {r.text[:400]}")
        continue
    run_id = r.json()["data"]["id"]
    print(f"  run started: {run_id}")
    # poll
    for _ in range(18):
        time.sleep(5)
        rs = c.get(f"https://api.apify.com/v2/acts/{aid}/runs/{run_id}", headers=h)
        st = rs.json()["data"]["status"]
        print(f"  [{st}]")
        if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "ERROR"):
            break
    if st == "SUCCEEDED":
        ds = rs.json()["data"].get("defaultDatasetId")
        if ds:
            rd = c.get(f"https://api.apify.com/v2/datasets/{ds}/items", headers=h, params={"limit": 50})
            items = rd.json()
            print(f"  dataset: {len(items)} items")
            if items:
                print("  sample item keys:", list(items[0].keys()))
                s = json.dumps(items[0], ensure_ascii=False, indent=2)
                print(s[:1800])
    else:
        rd_ = c.get(f"https://api.apify.com/v2/acts/{aid}/runs/{run_id}", headers=h)
        det = rd_.json()["data"]
        print(f"  final: status={det.get('status')} exitCode={det.get('exitCode')}")
        err = det.get("error")
        print(f"  error: {json.dumps(err, ensure_ascii=False)[:500] if err else 'n/a'}")
        # also show build/status message if any
        break
print("\nDONE")
