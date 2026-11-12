"""List all Actors the authenticated account can access."""
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

# List account's own actors
print("=== My Actors ===")
r = c.get("https://api.apify.com/v2/acts", headers=h, params={"my": "true", "limit": 100})
print(f"GET /v2/acts?my=true -> HTTP {r.status_code}")
if r.status_code == 200:
    data = r.json().get("data", {})
    items = data.get("items", [])
    print(f"  Found {len(items)} actors")
    for act in items[:20]:
        print(f"    {act.get('name')} ({act.get('id')}) - {act.get('title')}")
else:
    print(f"  body: {r.text[:500]}")

# Search for telegram/korean/news actors in the Store
print("\n=== Search Apify Store for 'telegram' ===")
r = c.get("https://api.apify.com/v2/store", headers=h, params={"search": "telegram", "limit": 10})
if r.status_code == 200:
    data = r.json().get("data", {})
    items = data.get("items", [])
    for act in items:
        print(f"  {act.get('username')}/{act.get('name')} - {act.get('title')}")
else:
    print(f"  HTTP {r.status_code}: {r.text[:300]}")

print("\n=== Search for 'naver stock' ===")
r = c.get("https://api.apify.com/v2/store", headers=h, params={"search": "naver stock", "limit": 10})
if r.status_code == 200:
    data = r.json().get("data", {})
    items = data.get("items", [])
    for act in items:
        print(f"  {act.get('username')}/{act.get('name')} - {act.get('title')}")
else:
    print(f"  HTTP {r.status_code}")

print("\n=== Search for 'korean news' ===")
r = c.get("https://api.apify.com/v2/store", headers=h, params={"search": "korean news", "limit": 10})
if r.status_code == 200:
    data = r.json().get("data", {})
    items = data.get("items", [])
    for act in items:
        print(f"  {act.get('username')}/{act.get('name')} - {act.get('title')}")
else:
    print(f"  HTTP {r.status_code}")

print("\n=== Search for 'hkgolden hong kong' ===")
r = c.get("https://api.apify.com/v2/store", headers=h, params={"search": "hong kong forum", "limit": 10})
if r.status_code == 200:
    data = r.json().get("data", {})
    items = data.get("items", [])
    for act in items:
        print(f"  {act.get('username')}/{act.get('name')} - {act.get('title')}")
else:
    print(f"  HTTP {r.status_code}")

print("\nDONE")
