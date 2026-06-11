from __future__ import annotations

import re

from django.conf import settings


def get_brand_mention_keyword() -> str:
    return (getattr(settings, "BRAND_MENTION_KEYWORD", None) or "ellaresort").lower()


def text_mentions_brand(text: str, keyword: str | None = None) -> bool:
    haystack = (text or "").lower()
    needle = (keyword or get_brand_mention_keyword()).lower()
    if needle in haystack:
        return True
    if needle == "ellaresort":
        return bool(re.search(r"ella[\s-]*resort", haystack))
    return False


def count_brand_mention_comments(video) -> int:
    """Tag stored comments and return how many mention the brand keyword."""
    from competitions.models import VideoComment

    keyword = get_brand_mention_keyword()
    mention_count = 0

    for comment in VideoComment.objects.filter(video=video).only("id", "text", "mentions_brand"):
        mentions = text_mentions_brand(comment.text, keyword)
        if comment.mentions_brand != mentions:
            comment.mentions_brand = mentions
            comment.save(update_fields=["mentions_brand"])
        if mentions:
            mention_count += 1

    return mention_count
