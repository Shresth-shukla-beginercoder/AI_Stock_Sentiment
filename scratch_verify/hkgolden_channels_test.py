"""HKGolden Actor test with correct input format (channels, not board)."""
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

# Canonical Actor ID from OpenAPI endpoint
actor_id = "fSZMN7Wfwuye4J8cd"

# Test HKGolden with correct input format
inputs = [
    {"mode": "channel", "channels": ["FN"], "maxItems": 5},  # Finance
    {"mode": "channel", "channels": ["CA"], "maxItems": 5},  # Current Affairs
]

for inp in inputs:
    print(f"\n--- Running with {json.dumps(inp)} ---")
    r = c.post(
        f"https://api.apify.com/v2/acts/{actor_id}/runs",
        headers=h,
        json=inp,
        params={"timeout": 120, "memory": 512},
    )
    print(f"  POST -> HTTP {r.status_code}")

    if r.status_code not in (200, 201):
        print(f"  Error: {r.text[:500]}")
        continue

    run_data = r.json()["data"]
    run_id = run_data["id"]
    print(f"  Run started: {run_id}")

    # Poll for completion
    status = "UNKNOWN"
    for _ in range(24):  # 24 * 5s = 120s
        time.sleep(5)
        rs = c.get(f"https://api.apify.com/v2/acts/{actor_id}/runs/{run_id}", headers=h)
        run_info = rs.json()["data"]
        status = run_info["status"]
        print(f"    Status: {status}")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "ERROR"):
            break

    if status == "SUCCEEDED":
        ds_id = run_info["defaultDatasetId"]
        rd = c.get(f"https://api.apify.com/v2/datasets/{ds_id}/items", headers=h, params={"limit": 10})
        items = rd.json()
        print(f"  ✓ Dataset: {len(items)} items")
        if items:
            print(f"  Sample item keys: {list(items[0].keys())}")
            # Show a sample
            sample = json.dumps(items[0], indent=2, ensure_ascii=False)
            print(f"  Sample:\n{sample[:800]}")
    else:
        print(f"  ✗ Run {status}")
        # Show error details if available
        error_info = run_info.get("error")
        if error_info:
            print(f"  Error: {json.dumps(error_info, indent=2, ensure_ascii=False)[:500]}")

print("\nDONE")
