import os
from app.collectors.apify import ApifySocialCollector
from app.core.config import get_settings

settings = get_settings()
collector = ApifySocialCollector(settings=settings)
# Testing verification
for actor in ["lofomachines/telegram-keyword-search-scraper", "claude_code_reviewer/lihkg-scraper-en"]:
    print(f"Verifying {actor}: {collector.verify_actor(actor)}")
