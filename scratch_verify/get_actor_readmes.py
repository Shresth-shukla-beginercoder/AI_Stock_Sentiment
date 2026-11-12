"""Get Actor READMEs and example inputs to understand required parameters."""
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
    "lofomachines~telegram-keyword-search-scraper",
    "hgservices~naver-stock-discussion-scraper",
    "ardent_fork~daum-news",
    "claude_code_reviewer~hkgolden-scraper",
]

for actor_ref in actors:
    print(f"\n{'='*70}")
    print(f"{actor_ref}")
    print('='*70)

    r = c.get(f"https://api.apify.com/v2/acts/{actor_ref}", headers=h)
    if r.status_code != 200:
        print(f"Error: HTTP {r.status_code}")
        continue

    d = r.json().get("data", {})

    # Get README
    r_readme = c.get(f"https://api.apify.com/v2/acts/{actor_ref}/readme", headers=h)
    if r_readme.status_code == 200:
        readme = r_readme.json().get("body", "")
        print("\n--- README ---")
        print(readme[:3000])

    # Get versions for example input
    vers = d.get("versions", [])
    if vers:
        v = vers[0]
        print(f"\n--- Default Version ---")
        print(f"versionNumber: {v.get('versionNumber')}")
        print(f"createdAt: {v.get('createdAt')}")

        # Example input
        ex_input = v.get("exampleRunInput")
        if ex_input:
            print(f"\n--- Example Input ---")
            print(json.dumps(ex_input, indent=2, ensure_ascii=False)[:2000])

        # Input schema (try different keys)
        for key in ["inputSchema", "input_schema", "schema"]:
            if key in v:
                print(f"\n--- {key} ---")
                print(json.dumps(v[key], indent=2, ensure_ascii=False)[:2000])
                break

print("\n\nDONE")
