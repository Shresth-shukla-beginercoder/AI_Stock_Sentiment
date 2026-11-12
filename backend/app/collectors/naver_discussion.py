from app.collectors.apify import ApifySocialCollector, SocialPostItem
from datetime import datetime
from app.collectors.normalize import clean_text, social_content_hash

class NaverDiscussionCollector(ApifySocialCollector):
    def to_social_items(self, raw_items: list[dict], *, platform: str = "naver") -> list[SocialPostItem]:
        out: list[SocialPostItem] = []
        for raw in raw_items:
            item = raw
            content = clean_text(item.get("text"))
            if not content: continue

            published = item.get("writtenAt") # Assumed format

            chash = social_content_hash(platform, content, str(item.get("postId")))
            out.append(SocialPostItem(
                source=platform,
                content_hash=chash,
                content=content,
                url=item.get("url"),
                published_at=published, # Normalized in Phase 6/9
                engagement=None, # views/likes exist, map if available
                external_id=str(item.get("postId"))
            ))
        return out
