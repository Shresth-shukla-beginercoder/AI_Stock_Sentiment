"""Check Actor public/access status and attempt to call them."""
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

actors = [
    "lofomachines/telegram-keyword-search-scraper",
    "hgservices/naver-stock-discussion-scraper",
    "ardent_fork/daum-news",
    "claude_code_reviewer/lihkg-scraper-en",
]

for actor_ref in actors:
    print(f"\n===== {actor_ref} =====")

    # Try to get actor details via the tasks endpoint (public actors)
    r = c.get(f"https://api.apify.com/v2/actor-tasks", headers=h, params={"actId": actor_ref})
    print(f"GET /v2/actor-tasks?actId={actor_ref} -> HTTP {r.status_code}")

    # Try calling the actor directly (minimal test input)
    print(f"Attempting to call actor with minimal input...")
    r = c.post(
        f"https://api.apify.com/v2/acts/{actor_ref}/runs",
        headers=h,
        json={"maxItems": 1},  # minimal bounded test
        params={"timeout": 60, "memory": 128}
    )
    print(f"POST /v2/acts/{actor_ref}/runs -> HTTP {r.status_code}")
    if r.status_code in (200, 201):
        body = r.json()
        run_id = body.get("data", {}).get("id")
        print(f"  RUN STARTED: id={run_id}")
    else:
        body_text = r.text[:400]
        print(f"  Error: {body_text}")

print("\nDONE")
