import re
from urllib.parse import urlparse

from rest_framework import serializers

PLATFORM_HOST_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "tiktok": [
        re.compile(r"^(?:www\.)?tiktok\.com$", re.I),
        re.compile(r"^vm\.tiktok\.com$", re.I),
        re.compile(r"^vt\.tiktok\.com$", re.I),
    ],
    "youtube": [
        re.compile(r"^(?:www\.)?youtube\.com$", re.I),
        re.compile(r"^youtu\.be$", re.I),
        re.compile(r"^(?:www\.)?m\.youtube\.com$", re.I),
    ],
    "instagram": [
        re.compile(r"^(?:www\.)?instagram\.com$", re.I),
    ],
    "facebook": [
        re.compile(r"^(?:www\.)?facebook\.com$", re.I),
        re.compile(r"^(?:www\.)?fb\.watch$", re.I),
    ],
}

VIDEO_PATH_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "tiktok": [
        re.compile(r"/@[^/]+/video/\d+", re.I),
        re.compile(r"^/t/[A-Za-z0-9]+", re.I),
    ],
    "youtube": [
        re.compile(r"^/watch", re.I),
        re.compile(r"^/shorts/", re.I),
        re.compile(r"^/[A-Za-z0-9_-]{11}$", re.I),
    ],
    "instagram": [
        re.compile(r"^/(?:p|reel|tv)/[A-Za-z0-9_-]+", re.I),
    ],
    "facebook": [
        re.compile(r"^/.+/videos/", re.I),
        re.compile(r"^/watch", re.I),
        re.compile(r"^/reel/", re.I),
    ],
}

CHANNEL_PATH_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "tiktok": [re.compile(r"^/@[^/]+/?$", re.I)],
    "youtube": [
        re.compile(r"^/@[^/]+/?$", re.I),
        re.compile(r"^/channel/[^/]+/?$", re.I),
        re.compile(r"^/c/[^/]+/?$", re.I),
    ],
    "instagram": [re.compile(r"^/[^/]+/?$", re.I)],
    "facebook": [re.compile(r"^/[^/]+/?$", re.I)],
}


def normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise serializers.ValidationError("URL is required.")
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        raise serializers.ValidationError("Enter a valid URL.")
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def host_matches_platform(host: str, platform: str) -> bool:
    patterns = PLATFORM_HOST_PATTERNS.get(platform, [])
    return any(pattern.match(host) for pattern in patterns)


def validate_social_channel_url(url: str, platform: str) -> str:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()

    if not host_matches_platform(host, platform):
        label = platform.replace("_", " ").title()
        raise serializers.ValidationError(
            f"Channel link must be a valid {label} profile URL."
        )

    path = parsed.path or "/"
    patterns = CHANNEL_PATH_PATTERNS.get(platform, [])
    if patterns and not any(pattern.match(path) for pattern in patterns):
        raise serializers.ValidationError(
            f"Enter a valid {platform} channel or profile URL."
        )

    return normalized


def validate_competition_video_url(url: str, platform: str) -> str:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.netloc.lower()

    if not host_matches_platform(host, platform):
        label = platform.replace("_", " ").title()
        raise serializers.ValidationError(
            f"Video link must be from {label} — the competition platform."
        )

    path = parsed.path or "/"

    if platform == "tiktok" and host in {"vm.tiktok.com", "vt.tiktok.com"}:
        return normalized

    patterns = VIDEO_PATH_PATTERNS.get(platform, [])
    if patterns and not any(pattern.search(path) for pattern in patterns):
        raise serializers.ValidationError(
            f"Enter a valid {platform} video URL for this competition."
        )

    return normalized


def extract_video_id(url: str, platform: str) -> str:
    parsed = urlparse(url)
    path = parsed.path

    if platform == "tiktok":
        match = re.search(r"/video/(\d+)", path)
        if match:
            return match.group(1)
        short = re.search(r"/t/([A-Za-z0-9]+)", path)
        if short:
            return short.group(1)
        return path.strip("/").split("/")[-1]

    if platform == "youtube":
        if parsed.netloc.lower() == "youtu.be":
            return path.strip("/").split("/")[0]
        from_query = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
        if from_query:
            return from_query.group(1)
        shorts = re.search(r"/shorts/([A-Za-z0-9_-]{11})", path)
        if shorts:
            return shorts.group(1)

    if platform == "instagram":
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", path)
        if match:
            return match.group(1)

    if platform == "facebook":
        return path.strip("/").replace("/", "_")[:120]

    return path.strip("/").split("/")[-1][:120]
