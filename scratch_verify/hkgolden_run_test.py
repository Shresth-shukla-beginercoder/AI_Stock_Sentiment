from apify_client import ApifyClient
from app.core.config import get_settings
import json

settings = get_settings()
token = settings.apify_token()
client = ApifyClient(token)

actor_id = "fSZMN7Wfwuye4J8cd" # Canonical ID from previous discovery

run_input = {
    "mode": "channel",
    "channels": ["FN"], # Finance board
    "maxItems": 5,
    "proxyConfiguration": {"useApifyProxy": True}
}

print(f"Running HKGolden actor {actor_id}...")
try:
    run = client.actor(actor_id).call(run_input=run_input)
    print(f"Run status: {run['status']}")

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"Retrieved {len(items)} items")
    if items:
        print(json.dumps(items[0], indent=2, ensure_ascii=False))

except Exception as e:
    print(f"Error: {e}")
