from __future__ import annotations

import re

from django.conf import settings


def normalize_comment_match_terms(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[\n,]+", raw)
    elif isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        return []

    seen: set[str] = set()
    terms: list[str] = []
    for part in parts:
        token = part.strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(token)
    return terms


def get_brand_mention_keyword() -> str:
    return (getattr(settings, "BRAND_MENTION_KEYWORD", None) or "ellaresort").lower()


def text_matches_comment_terms(text: str, terms: list[str]) -> bool:
    if not terms:
        return False

    haystack = (text or "").lower()
    for term in terms:
        token = term.strip().lower()
        if not token:
            continue
        if token in haystack:
            return True

        bare = token.lstrip("@#")
        if bare and bare in haystack:
            return True
        if bare == "ellaresort" and re.search(r"ella[\s-]*resort", haystack):
            return True
    return False


def text_mentions_brand(text: str, keyword: str | None = None) -> bool:
    return text_matches_comment_terms(text, [keyword or get_brand_mention_keyword()])


def count_matching_stored_comments(video, terms: list[str]) -> int:
    from competitions.models import VideoComment

    mention_count = 0
    to_update: list = []

    for comment in VideoComment.objects.filter(video=video).only(
        "id",
        "text",
        "mentions_brand",
    ):
        mentions = text_matches_comment_terms(comment.text, terms)
        if mentions:
            mention_count += 1
        if comment.mentions_brand != mentions:
            comment.mentions_brand = mentions
            to_update.append(comment)

    if to_update:
        VideoComment.objects.bulk_update(to_update, ["mentions_brand"])

    return mention_count


def compute_scored_comment_count(video) -> int:
    """Comments that count toward the competition Comments metric."""
    competition = video.competition
    platform_total = int(video.comments or 0)

    if not competition.uses_matched_comment_scoring():
        return platform_total

    terms = competition.get_comment_match_terms()
    matched = count_matching_stored_comments(video, terms)
    if matched > 0:
        return matched

    # No synced comment text yet — keep platform total until text is available.
    return platform_total


def count_brand_mention_comments(video) -> int:
    """Comments that count toward the Brand mentions metric."""
    competition = video.competition
    terms = competition.get_comment_match_terms()

    if competition.uses_matched_comment_scoring():
        return count_matching_stored_comments(video, terms)

    keyword = get_brand_mention_keyword()
    return count_matching_stored_comments(video, [keyword])


def refresh_video_comment_scores(video, *, persist: bool = False) -> tuple[int, int]:
    scored = compute_scored_comment_count(video)
    brand_mentions = count_brand_mention_comments(video)
    video.scored_comments = scored
    video.brand_mention_comments = brand_mentions

    if persist:
        video.save(
            update_fields=[
                "scored_comments",
                "brand_mention_comments",
                "updated_at",
            ]
        )
    return scored, brand_mentions
