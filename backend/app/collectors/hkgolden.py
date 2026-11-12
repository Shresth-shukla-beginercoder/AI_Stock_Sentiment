from app.collectors.apify import ApifySocialCollector, SocialPostItem
from app.collectors.normalize import clean_text, social_content_hash, parse_timestamp

class HKGoldenCollector(ApifySocialCollector):
    def to_social_items(self, raw_items: list[dict], *, platform: str = "hkgolden") -> list[SocialPostItem]:
        out: list[SocialPostItem] = []
        for item in raw_items:
            content = clean_text(item.get("content"))
            if not content: continue

            chash = social_content_hash(platform, content, str(item.get("reply_id") or item.get("topic_id")))
            published = parse_timestamp(item.get("created_at"))

            out.append(SocialPostItem(
                source=platform,
                content_hash=chash,
                content=content,
                url=item.get("topic_url"),
                published_at=published,
                engagement=item.get("marks_good"),
                external_id=str(item.get("reply_id") or item.get("topic_id"))
            ))
        return out
