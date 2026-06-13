from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import httpx

from competitions.validators import normalize_url

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _canonicalize_tiktok_path(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host == "tiktok.com":
        host = "www.tiktok.com"
    path = parsed.path.rstrip("/") or "/"

    mobile = re.search(r"^/v/(\d+)(?:\.html)?$", path, re.I)
    if mobile:
        path = f"/video/{mobile.group(1)}"

    if re.search(r"/@[^/]+/video/\d+", path, re.I):
        return f"https://{host}{path}"

    video_only = re.search(r"^/video/(\d+)$", path, re.I)
    if video_only:
        return f"https://www.tiktok.com/video/{video_only.group(1)}"

    return f"https://{host}{path}"


def _resolved_video_url(candidate: str) -> str | None:
    parsed_path = urlparse(candidate).path or ""
    if re.search(r"/(?:@[^/]+/)?video/\d+", parsed_path, re.I):
        return _canonicalize_tiktok_path(normalize_url(candidate))
    mobile = re.search(r"/v/(\d+)", parsed_path, re.I)
    if mobile:
        return f"https://www.tiktok.com/video/{mobile.group(1)}"
    return None


def resolve_tiktok_video_url(url: str) -> str:
    """Follow redirects and normalize to a stable TikTok video URL."""
    normalized = normalize_url(url)
    direct = _resolved_video_url(normalized)
    if direct:
        return direct

    try:
        with httpx.Client(timeout=8.0, follow_redirects=True) as http:
            response = http.get(normalized, headers=BROWSER_HEADERS)
            final_url = str(response.url)
            resolved = _resolved_video_url(final_url)
            if resolved:
                return resolved
    except Exception as exc:
        logger.debug("HTTP URL resolve failed for %s: %s", normalized, exc)

    return _canonicalize_tiktok_path(normalized)
