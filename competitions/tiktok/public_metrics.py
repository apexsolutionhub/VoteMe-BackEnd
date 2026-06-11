from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def fetch_public_tiktok_metrics(video_url: str) -> dict[str, int] | None:
    """Best-effort public stats scrape when TikTok OAuth is unavailable."""
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as http:
            response = http.get(
                video_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            response.raise_for_status()
            html = response.text
    except Exception as exc:
        logger.warning("Public TikTok fetch failed for %s: %s", video_url, exc)
        return None

    stats_match = re.search(
        r'"stats"\s*:\s*\{[^}]*"playCount"\s*:\s*(\d+)[^}]*"diggCount"\s*:\s*(\d+)'
        r'[^}]*"commentCount"\s*:\s*(\d+)[^}]*"shareCount"\s*:\s*(\d+)',
        html,
    )
    if stats_match:
        return {
            "views": int(stats_match.group(1)),
            "likes": int(stats_match.group(2)),
            "comments": int(stats_match.group(3)),
            "shares": int(stats_match.group(4)),
        }

    def grab(field: str) -> int | None:
        match = re.search(rf'"{field}"\s*:\s*(\d+)', html)
        return int(match.group(1)) if match else None

    views = grab("playCount")
    if views is None:
        return None

    return {
        "views": views,
        "likes": grab("diggCount") or 0,
        "comments": grab("commentCount") or 0,
        "shares": grab("shareCount") or 0,
    }
